"""
Policy Reasoner node.

Pipeline:
  1. Build a retrieval query from packet form_data + damage/document findings
  2. Retrieve top-k policy chunks via hybrid RAG (BM25 + dense + RRF + reranker)
  3. Run LLM over the retrieved clauses to produce PolicyFinding objects with
     clause-level citations (clause_id, corpus_layer, determination, cited_text)

The retriever is lazy-loaded on first call (triggers model download on cold start).
Pass a pre-built RetrievalOrchestrator in tests to avoid downloads.

Status: SUCCESS (findings produced), PARTIAL (retrieval succeeded but no findings or
        LLM parse error recovered), FAILED (retriever/LLM error after retries),
        SKIPPED (never — policy reasoning always runs).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

import litellm
from pydantic import BaseModel, Field, ValidationError

from ingestion.models import ClaimPacket
from orchestration.nodes.base import Node, NodeResult
from orchestration.state import AgentStatus, EvidenceStore, PolicyFinding
from rag.retrieval.orchestrator import RetrievalConfig, RetrievalOrchestrator

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_CORPUS_DIR = Path(os.getenv("VERICLAIM_CORPUS_DIR", "data/synthetic/vericlaim_mutual"))
_TOP_K = int(os.getenv("VERICLAIM_POLICY_TOP_K", "8"))
_MAX_PARSE_RETRIES = 2

_REASONING_PROMPT = """\
{degraded_notice}\
You are an insurance policy analyst. Based on the claim summary and the retrieved \
policy clauses below, determine coverage for each aspect of the claim.

CLAIM SUMMARY:
{claim_summary}

RETRIEVED POLICY CLAUSES:
{clauses}

For each coverage determination provide:
- clause_id: exact clause ID from the header (e.g. PART_D.3, ENDORSEMENT_VC001.1)
- corpus_layer: "policy", "endorsement", "regulation", or "guideline"
- determination: "covered", "denied", "partial", "ambiguous", or "needs_review"
- cited_text: verbatim excerpt (max 200 chars) that supports the determination
- confidence: 0.0–1.0
- endorsements_applied: list of endorsement IDs that modified this determination

Respond with valid JSON only, no markdown fences:
{{
  "findings": [
    {{
      "clause_id": "...",
      "corpus_layer": "policy|endorsement|regulation|guideline",
      "determination": "covered|denied|partial|ambiguous|needs_review",
      "cited_text": "...",
      "confidence": 0.0,
      "endorsements_applied": []
    }}
  ]
}}"""


class _PolicyFindingRaw(BaseModel):
    clause_id: str
    corpus_layer: str
    determination: str
    cited_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    endorsements_applied: list[str] = Field(default_factory=list)


class _PolicyReasoningResponse(BaseModel):
    findings: list[_PolicyFindingRaw]


_VALID_CORPUS_LAYERS = {"policy", "endorsement", "regulation", "guideline"}
_VALID_DETERMINATIONS = {"covered", "denied", "partial", "ambiguous", "needs_review"}


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


def _build_retrieval_query(store: EvidenceStore, packet: ClaimPacket) -> str:
    parts: list[str] = []
    description = str(packet.form_data.get("description", "")).strip()
    if description:
        parts.append(description)
    if store.damage_findings:
        categories = sorted({f.category for f in store.damage_findings})
        parts.append(f"damage: {', '.join(categories)}")
        if any(f.category == "total_loss" for f in store.damage_findings):
            parts.append("total loss")
    if store.document_findings:
        fields = {f.field_name: f.value for f in store.document_findings}
        if "coverage_type" in fields:
            parts.append(f"coverage type: {fields['coverage_type']}")
    return " ".join(parts) or "insurance claim coverage determination"


def _build_claim_summary(store: EvidenceStore, packet: ClaimPacket) -> str:
    lines = [f"Claim ID: {store.claim_id}"]
    if packet.claim_type:
        lines.append(f"Claim type: {packet.claim_type.value}")
    description = str(packet.form_data.get("description", "")).strip()
    if description:
        lines.append(f"Description: {description}")
    if store.damage_findings:
        total_cost = sum(f.estimated_cost_usd for f in store.damage_findings)
        categories = sorted({f.category for f in store.damage_findings})
        lines.append(
            f"Damage: {len(store.damage_findings)} regions, "
            f"~${total_cost:.0f} total, categories: {categories}"
        )
    if store.document_findings:
        fields = {f.field_name: f.value for f in store.document_findings}
        for key in ("date_of_loss", "coverage_type", "policy_number"):
            if key in fields:
                lines.append(f"{key}: {fields[key]}")
    return "\n".join(lines)


def _format_clauses(chunks: list[tuple]) -> str:
    lines: list[str] = []
    for chunk, score in chunks:
        header = f"[{chunk.chunk_id}] score={score:.4f}"
        if chunk.path:
            header += f"  path: {' > '.join(chunk.path)}"
        lines.append(header)
        lines.append(chunk.text[:700])
        lines.append("")
    return "\n".join(lines)


class PolicyReasonerNode(Node):
    """
    Retrieves policy clauses via hybrid RAG and reasons over them to produce
    PolicyFinding objects with clause-level citations.
    """

    def __init__(
        self,
        corpus_dir: Path | None = None,
        retriever: RetrievalOrchestrator | None = None,
    ) -> None:
        self._corpus_dir = corpus_dir or _CORPUS_DIR
        self._retriever = retriever  # inject in tests to skip model downloads
        self._retriever_built = retriever is not None

    def _get_retriever(self) -> RetrievalOrchestrator:
        if not self._retriever_built:
            self._retriever = RetrievalOrchestrator.from_corpus_dir(
                self._corpus_dir,
                RetrievalConfig(top_k_per_retriever=_TOP_K, top_k_rerank=_TOP_K),
            )
            self._retriever_built = True
        return self._retriever  # type: ignore[return-value]

    @property
    def name(self) -> str:
        return "policy_reasoner"

    @property
    def timeout_s(self) -> float:
        return 120.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        try:
            retriever = self._get_retriever()
        except Exception as e:
            logger.error("Failed to build retriever: %s", e)
            return NodeResult(
                store=self._delta(store, AgentStatus.FAILED),
                status=AgentStatus.FAILED,
            )

        query = _build_retrieval_query(store, packet)
        try:
            chunks = await retriever.retrieve(query, top_k=_TOP_K)
        except Exception as e:
            logger.error("Retrieval failed: %s", e)
            return NodeResult(
                store=self._delta(store, AgentStatus.FAILED),
                status=AgentStatus.FAILED,
            )

        if not chunks:
            return NodeResult(
                store=self._delta(store, AgentStatus.PARTIAL),
                status=AgentStatus.PARTIAL,
            )

        degraded_notice = ""
        if degraded_context:
            notice_lines = "\n".join(f"- {v}" for v in degraded_context.values())
            degraded_notice = f"Context notes from upstream failures:\n{notice_lines}\n\n"

        prompt = _REASONING_PROMPT.format(
            degraded_notice=degraded_notice,
            claim_summary=_build_claim_summary(store, packet),
            clauses=_format_clauses(chunks),
        )

        parse_error: str | None = None
        reasoned: _PolicyReasoningResponse | None = None
        cost_usd = 0.0

        for attempt in range(_MAX_PARSE_RETRIES + 1):
            full_prompt = (
                prompt
                if not parse_error
                else f"{prompt}\n\nPrevious parse error — return valid JSON only: {parse_error}"
            )
            response = await litellm.acompletion(
                model=_MODEL,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.0,
            )
            try:
                cost_usd += litellm.completion_cost(completion_response=response)
            except Exception:
                pass

            raw = response.choices[0].message.content or ""
            try:
                reasoned = _PolicyReasoningResponse.model_validate(
                    json.loads(_strip_fences(raw))
                )
                break
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt < _MAX_PARSE_RETRIES:
                    parse_error = str(e)
                    logger.warning(
                        "Policy reasoning parse error (attempt %d): %s", attempt + 1, e
                    )
                else:
                    logger.error("Policy reasoning failed after retries: %s", e)
                    return NodeResult(
                        store=self._delta(store, AgentStatus.FAILED),
                        status=AgentStatus.FAILED,
                        cost_usd=cost_usd,
                    )

        assert reasoned is not None
        findings: list[PolicyFinding] = []
        for raw_f in reasoned.findings:
            if raw_f.corpus_layer not in _VALID_CORPUS_LAYERS:
                logger.warning("Ignoring finding with unknown corpus_layer: %r", raw_f.corpus_layer)
                continue
            if raw_f.determination not in _VALID_DETERMINATIONS:
                logger.warning("Ignoring finding with unknown determination: %r", raw_f.determination)
                continue
            findings.append(
                PolicyFinding(
                    clause_id=raw_f.clause_id,
                    corpus_layer=raw_f.corpus_layer,  # type: ignore[arg-type]
                    determination=raw_f.determination,  # type: ignore[arg-type]
                    cited_text=raw_f.cited_text,
                    confidence=raw_f.confidence,
                    endorsements_applied=raw_f.endorsements_applied,
                )
            )

        status = AgentStatus.SUCCESS if findings else AgentStatus.PARTIAL
        return NodeResult(
            store=self._delta(store, status, policy_findings=findings),
            status=status,
            cost_usd=cost_usd,
            metadata={
                "retrieved_chunk_count": len(chunks),
                "findings_count": len(findings),
            },
        )
