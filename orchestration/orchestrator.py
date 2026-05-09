"""
Async orchestrator — the only coordinator in the system.

Executes the static DAG in topological stage order, running each stage with
asyncio.gather. Handles per-node timeouts, retry dispatch, and trace emission.
The orchestrator is code, not an LLM.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

# Bridge API_BASE_URL → OPENAI_API_BASE so LiteLLM picks it up automatically.
# This runs once when the orchestrator is imported, before any LLM call is made.
if _api_base := os.getenv("API_BASE_URL"):
    os.environ["OPENAI_API_BASE"] = _api_base

from ingestion.intake import load_claim_from_manifest, validate_claim_packet
from ingestion.models import ClaimPacket
from ingestion.router import ClaimRouter
from orchestration.failure.retry import FailureType, RetryConfig, retry_with_backoff
from orchestration.graph import topological_stages
from orchestration.nodes.base import Node, NodeResult
from orchestration.persistence.state_store import ClaimStateStore
from orchestration.persistence.trace_store import TraceStore
from orchestration.state import AgentStatus, ClaimRecord, ClaimState, EvidenceStore

logger = logging.getLogger(__name__)

_router = ClaimRouter()
_state_store = ClaimStateStore()
_trace_store = TraceStore()


def _get_node_registry() -> dict[str, Node]:
    """
    Lazy import of all node implementations.
    Nodes not yet implemented are stubs that return SKIPPED.
    """
    from orchestration.nodes.adjudicator import AdjudicatorNode
    from orchestration.nodes.consistency_auditor import ConsistencyAuditorNode
    from orchestration.nodes.damage_assessor import DamageAssessorNode
    from orchestration.nodes.document_extractor import DocumentExtractorNode
    from orchestration.nodes.fraud_aggregator import FraudAggregatorNode
    from orchestration.nodes.output_drafter import OutputDrafterNode
    from orchestration.nodes.policy_reasoner import PolicyReasonerNode
    from orchestration.nodes.statement_analyst import StatementAnalystNode

    return {
        "damage_assessor": DamageAssessorNode(),
        "document_extractor": DocumentExtractorNode(),
        "statement_analyst": StatementAnalystNode(),
        "policy_reasoner": PolicyReasonerNode(),
        "fraud_aggregator": FraudAggregatorNode(),
        "consistency_auditor": ConsistencyAuditorNode(),
        "adjudicator": AdjudicatorNode(),
        "output_drafter": OutputDrafterNode(),
    }


async def _run_node(
    node: Node,
    store: EvidenceStore,
    packet: ClaimPacket,
    degraded_context: dict[str, str] | None = None,
    attempt: int = 1,
) -> EvidenceStore:
    """Run a single node with its configured timeout and retry policy."""
    idempotency_key = f"{store.claim_id}_{node.name}_{attempt}"
    logger.debug("Running node %s (attempt %d, key=%s)", node.name, attempt, idempotency_key)

    start = time.monotonic()
    try:
        result: NodeResult = await asyncio.wait_for(
            node.run(store, packet, degraded_context),
            timeout=node.timeout_s,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        node_meta = result.metadata or {}
        _trace_store.record_node(
            claim_id=store.claim_id,
            node_name=node.name,
            attempt=attempt,
            status=result.status.value,
            elapsed_ms=elapsed_ms,
            cost_usd=result.cost_usd,
            model_used=node_meta.get("model_used"),
            prompt_hash=node_meta.get("prompt_hash"),
            claim_type=packet.claim_type.value if packet.claim_type else None,
            severity_bucket=node_meta.get("severity_bucket"),
            metadata=node_meta if node_meta else None,
        )
        return result.store

    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Node %s timed out after %ds", node.name, node.timeout_s)
        _trace_store.record_node(
            claim_id=store.claim_id,
            node_name=node.name,
            attempt=attempt,
            status=AgentStatus.TIMEOUT.value,
            elapsed_ms=elapsed_ms,
            cost_usd=0.0,
            failure_type=FailureType.TRANSIENT.value,
            claim_type=packet.claim_type.value if packet.claim_type else None,
        )
        return EvidenceStore(claim_id=store.claim_id).mark_agent(node.name, AgentStatus.TIMEOUT)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        failure_type = FailureType.classify(e)
        logger.error("Node %s failed (type=%s): %s", node.name, failure_type.value, e)
        _trace_store.record_node(
            claim_id=store.claim_id,
            node_name=node.name,
            attempt=attempt,
            status=AgentStatus.FAILED.value,
            elapsed_ms=elapsed_ms,
            cost_usd=0.0,
            failure_type=failure_type.value,
            error=str(e),
            claim_type=packet.claim_type.value if packet.claim_type else None,
        )
        if RetryConfig.is_retryable(failure_type) and attempt < RetryConfig.max_attempts(failure_type):
            backoff = RetryConfig.backoff_s(attempt)
            logger.info("Retrying node %s in %.1fs", node.name, backoff)
            await asyncio.sleep(backoff)
            return await _run_node(node, store, packet, degraded_context, attempt + 1)

        return EvidenceStore(claim_id=store.claim_id).mark_agent(node.name, AgentStatus.FAILED)


async def run_claim(manifest_dir: Path | str) -> EvidenceStore:
    """
    End-to-end claim processing pipeline.

    Loads the claim packet, routes it, then executes the static DAG in
    topological stage order. All specialist failures are recorded in the
    EvidenceStore; the graph always runs to completion.

    Returns the final EvidenceStore after all stages have run.
    """
    manifest_dir = Path(manifest_dir)

    # --- Ingestion ---
    packet = load_claim_from_manifest(manifest_dir)
    warnings = validate_claim_packet(packet)
    for w in warnings:
        logger.warning("[%s] %s", packet.claim_id, w)

    record = ClaimRecord(claim_id=packet.claim_id)
    _state_store.upsert(record)

    # --- Routing ---
    record = record.transition(ClaimState.ROUTING)
    _state_store.upsert(record)
    decision = _router.route(packet)
    packet = packet.model_copy(update={"claim_type": decision.claim_type})
    record = record.model_copy(update={
        "claim_type": decision.claim_type.value,
        "routing_confidence": decision.confidence,
    })
    logger.info(
        "[%s] Routed to %s (conf=%.2f, src=%s)",
        packet.claim_id, decision.claim_type.value, decision.confidence, decision.source,
    )

    # --- Evidence gathering + reasoning ---
    store = EvidenceStore(claim_id=packet.claim_id)
    registry = _get_node_registry()
    stages = topological_stages()

    from orchestration.failure.degradation import get_degraded_context

    # Stage 0 is "router" — handled above; skip it in the node loop
    stage_label_map = [
        (ClaimState.ROUTING, stages[0]),
        (ClaimState.EVIDENCE_GATHERING, stages[1] if len(stages) > 1 else []),
        (ClaimState.REASONING, stages[2] if len(stages) > 2 else []),
        (ClaimState.ADJUDICATING, stages[3] if len(stages) > 3 else []),
        (ClaimState.DRAFTING, stages[4] if len(stages) > 4 else []),
    ]

    for state, stage_nodes in stage_label_map[1:]:  # skip router stage
        if not stage_nodes:
            continue
        record = record.transition(state)
        _state_store.upsert(record)

        # Inject degraded context for nodes that have upstream failures
        degraded_ctx = get_degraded_context(store)
        logger.debug("[%s] Stage %s: running %s", packet.claim_id, state.value, stage_nodes)

        tasks = [
            _run_node(registry[n], store.model_copy(), packet, degraded_ctx)
            for n in stage_nodes
            if n in registry
        ]
        results: list[EvidenceStore] = await asyncio.gather(*tasks)

        # Merge all stage results into the shared store
        for result_store in results:
            for agent_name, agent_status in result_store.specialist_status.items():
                store = store.mark_agent(agent_name, agent_status)
            store = store.model_copy(update={
                "damage_findings": store.damage_findings + result_store.damage_findings,
                "document_findings": store.document_findings + result_store.document_findings,
                "statement_findings": store.statement_findings + result_store.statement_findings,
                "policy_findings": store.policy_findings + result_store.policy_findings,
                "fraud_signals": store.fraud_signals + result_store.fraud_signals,
                "consistency_flags": store.consistency_flags + result_store.consistency_flags,
            })

    # --- Completion ---
    adjudicator_status = store.specialist_status.get("adjudicator")
    final_state = (
        ClaimState.HUMAN_REVIEW
        if adjudicator_status in (AgentStatus.FAILED, AgentStatus.TIMEOUT, AgentStatus.PARTIAL)
        or any(
            s in (AgentStatus.FAILED, AgentStatus.TIMEOUT)
            for s in store.specialist_status.values()
        )
        else ClaimState.COMPLETE
    )
    record = record.transition(final_state)
    _state_store.upsert(record)
    logger.info("[%s] Pipeline complete → %s", packet.claim_id, final_state.value)

    return store


if __name__ == "__main__":
    import argparse
    import json

    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Run a claim through the VeriClaim pipeline.")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    args = parser.parse_args()

    result = asyncio.run(run_claim(args.manifest_dir))
    print(json.dumps(result.model_dump(mode="json"), indent=2))
