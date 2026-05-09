"""
Downstream prompt adaptation based on upstream specialist failures.

When a Stage 2 specialist fails, Stage 3 specialists and the Adjudicator must
know not to reference missing evidence. This module produces per-node prompt
amendments that the orchestrator injects into each node's context.
"""
from __future__ import annotations

from orchestration.state import AgentStatus, EvidenceStore

# Nodes whose failure changes what downstream agents are allowed to reference
_FAILURE_MESSAGES: dict[str, str] = {
    "damage_assessor": (
        "IMPORTANT: The damage assessment specialist failed and produced no findings. "
        "Do NOT reference damage findings, cost estimates, or severity assessments. "
        "If damage assessment is required for a determination, route to HUMAN_REVIEW."
    ),
    "document_extractor": (
        "IMPORTANT: Document extraction failed. No structured fields from PDFs are available. "
        "Do NOT reference extracted document fields. "
        "If document evidence is required for a determination, route to HUMAN_REVIEW."
    ),
    "statement_analyst": (
        "IMPORTANT: Statement analysis failed. No verbal statement findings are available. "
        "Do NOT reference claimant statement cross-references."
    ),
    "policy_reasoner": (
        "IMPORTANT: Policy reasoning failed. No coverage determinations are available. "
        "Do NOT make coverage assertions. Route to HUMAN_REVIEW."
    ),
    "fraud_aggregator": (
        "IMPORTANT: Fraud signal aggregation failed. No fraud risk signals are available. "
        "Treat fraud risk as indeterminate and note this in your output."
    ),
    "consistency_auditor": (
        "IMPORTANT: Consistency audit failed. Cross-modal consistency has not been verified. "
        "Note this uncertainty in your output."
    ),
}

_PARTIAL_MESSAGES: dict[str, str] = {
    "damage_assessor": (
        "NOTE: Damage assessment returned partial results. "
        "Some damage findings may be incomplete — weight them with lower confidence."
    ),
    "document_extractor": (
        "NOTE: Document extraction returned partial results. "
        "Some document fields may be missing or low-confidence."
    ),
}


def get_degraded_context(store: EvidenceStore) -> dict[str, str]:
    """
    Return a dict of {node_name: amendment_text} for nodes that need to adapt
    their behavior because of upstream failures.

    The orchestrator passes the relevant amendments to each downstream node's run().
    """
    amendments: dict[str, str] = {}

    for agent_name, status in store.specialist_status.items():
        if status in (AgentStatus.FAILED, AgentStatus.TIMEOUT):
            if msg := _FAILURE_MESSAGES.get(agent_name):
                amendments[agent_name] = msg
        elif status == AgentStatus.PARTIAL:
            if msg := _PARTIAL_MESSAGES.get(agent_name):
                amendments[agent_name] = msg

    return amendments


def format_degradation_block(store: EvidenceStore) -> str:
    """
    Format all degradation amendments as a single block for inclusion in a prompt.
    Returns empty string if no degradation occurred.
    """
    amendments = get_degraded_context(store)
    if not amendments:
        return ""
    lines = ["=== UPSTREAM SPECIALIST STATUS ==="]
    for msg in amendments.values():
        lines.append(msg)
    lines.append("=================================")
    return "\n".join(lines)
