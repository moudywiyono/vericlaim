"""
Pre-adjudication refusal and escalation logic.

Evaluated before the Adjudicator calls the LLM. If conditions warrant refusal,
the adjudicator short-circuits and marks the claim for human review rather than
producing an LLM determination.

Refusal conditions:
- High-confidence fraud signals (severity=high, confidence>=0.8) → human review
- Two or more critical consistency flags → human review
- No policy findings available → fail (policy reasoner must run first)
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestration.state import EvidenceStore

_HIGH_FRAUD_CONFIDENCE_THRESHOLD = 0.8
_CRITICAL_FLAG_ESCALATION_THRESHOLD = 2


@dataclass
class RefusalDecision:
    should_refuse: bool
    reason: str
    escalate_to_human: bool


def evaluate_refusal(store: EvidenceStore) -> RefusalDecision:
    """
    Determine whether the adjudicator should refuse or escalate before reasoning.

    Returns a RefusalDecision with should_refuse=False if it's safe to proceed.
    """
    # High-confidence fraud → human review
    high_fraud = [
        s
        for s in store.fraud_signals
        if s.severity == "high" and s.confidence >= _HIGH_FRAUD_CONFIDENCE_THRESHOLD
    ]
    if high_fraud:
        signal_names = ", ".join(s.signal_type for s in high_fraud)
        return RefusalDecision(
            should_refuse=True,
            reason=f"High-confidence fraud signals detected: {signal_names}",
            escalate_to_human=True,
        )

    # Multiple critical consistency flags → human review
    critical_flags = [f for f in store.consistency_flags if f.severity == "critical"]
    if len(critical_flags) >= _CRITICAL_FLAG_ESCALATION_THRESHOLD:
        return RefusalDecision(
            should_refuse=True,
            reason=(
                f"{len(critical_flags)} critical consistency flags require human review: "
                + "; ".join(f.flag_type for f in critical_flags)
            ),
            escalate_to_human=True,
        )

    # No policy findings → can't adjudicate
    if not store.policy_findings:
        return RefusalDecision(
            should_refuse=True,
            reason=(
                "No policy findings available — PolicyReasonerNode must run "
                "before AdjudicatorNode"
            ),
            escalate_to_human=False,
        )

    return RefusalDecision(should_refuse=False, reason="", escalate_to_human=False)
