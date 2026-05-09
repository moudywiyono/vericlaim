"""
Output Drafter node.

Synthesizes the final claimant-facing settlement letter from the full EvidenceStore.
Rather than depending on the Adjudicator's unstructured output (which isn't stored
in the EvidenceStore), the Drafter reads structured findings directly:
  - policy_findings: clause-level determinations with cited text
  - damage_findings: repair cost estimates
  - fraud_signals / consistency_flags: to determine if review language is needed

The LLM produces a professional, plain-English settlement letter.

Status: SUCCESS (letter generated),
        PARTIAL (letter empty or LLM partially succeeded),
        FAILED (LLM call failed).
"""
from __future__ import annotations

import logging
import os
from typing import Literal

import litellm

from ingestion.models import ClaimPacket
from orchestration.nodes.base import Node, NodeResult
from orchestration.state import AgentStatus, EvidenceStore

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")

_DRAFT_PROMPT = """\
You are a professional claims adjuster at VeriClaim Mutual Insurance Company.
Write a formal settlement letter to the claimant based on the adjudication summary below.

CLAIM ID: {claim_id}
OVERALL DETERMINATION: {overall_determination}
TOTAL COVERAGE AMOUNT: ${coverage_amount_usd:.2f}
HUMAN REVIEW REQUIRED: {human_review}

ITEMIZED POLICY DETERMINATIONS:
{policy_determinations}

DAMAGE SUMMARY:
{damage_summary}

Write a letter that:
1. States the overall determination clearly in the opening paragraph
2. Itemizes each coverage determination with the relevant policy clause number
3. Explains any denials or exclusions in plain language the claimant can understand
4. States next steps (payment timeline if covered, appeal rights and 30-day deadline if denied)
5. Includes this exact regulatory notice at the end:
   "This determination is made pursuant to the terms and conditions of your policy.
   You have the right to appeal this decision within 30 days of this letter."
6. If human review is required, explain that an adjuster will contact them within 5 business days

Keep the tone professional but empathetic. Write the full letter text only."""


def _derive_overall_determination(
    store: EvidenceStore,
) -> tuple[Literal["covered", "partial", "denied", "human_review"], float]:
    """Derive overall determination and coverage amount from policy findings."""
    if not store.policy_findings:
        high_fraud = any(s.severity == "high" for s in store.fraud_signals)
        return ("human_review" if high_fraud else "denied"), 0.0

    determinations = [f.determination for f in store.policy_findings]
    total_damage = sum(f.estimated_cost_usd for f in store.damage_findings)

    # Human review if any finding is ambiguous and fraud signals present
    if "needs_review" in determinations and store.fraud_signals:
        return "human_review", 0.0

    covered_count = sum(1 for d in determinations if d in ("covered", "partial"))
    denied_count = sum(1 for d in determinations if d == "denied")

    if covered_count == 0:
        return "denied", 0.0
    if denied_count == 0:
        coverage = total_damage * 0.9  # rough estimate after deductibles
        return "covered", max(coverage, 0.0)

    # Mixed: partial determination
    coverage_ratio = covered_count / max(len(determinations), 1)
    return "partial", total_damage * coverage_ratio * 0.9


class OutputDrafterNode(Node):
    """
    Produces the claimant-facing settlement letter from structured EvidenceStore data.
    """

    @property
    def name(self) -> str:
        return "output_drafter"

    @property
    def timeout_s(self) -> float:
        return 60.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        overall, coverage_usd = _derive_overall_determination(store)
        human_review = overall == "human_review" or any(
            s.severity == "high" and s.confidence >= 0.8 for s in store.fraud_signals
        )

        policy_lines = "\n".join(
            f"  [{f.clause_id}] {f.determination.upper()}: {f.cited_text[:150]}"
            for f in store.policy_findings
        ) or "  No policy determinations available."

        damage_lines = "\n".join(
            f"  - {f.region_id}: {f.category}, ~${f.estimated_cost_usd:.0f}"
            for f in store.damage_findings
        ) or "  No damage findings available."

        prompt = _DRAFT_PROMPT.format(
            claim_id=store.claim_id,
            overall_determination=overall.upper(),
            coverage_amount_usd=coverage_usd,
            human_review="YES — Adjuster will contact you" if human_review else "No",
            policy_determinations=policy_lines,
            damage_summary=damage_lines,
        )

        cost_usd = 0.0
        letter_text = ""
        try:
            response = await litellm.acompletion(
                model=_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            try:
                cost_usd += litellm.completion_cost(completion_response=response)
            except Exception:
                pass
            letter_text = (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error("Output drafting failed: %s", e)
            return NodeResult(
                store=self._delta(store, AgentStatus.FAILED),
                status=AgentStatus.FAILED,
            )

        status = AgentStatus.SUCCESS if letter_text else AgentStatus.PARTIAL
        return NodeResult(
            store=self._delta(store, status),
            status=status,
            cost_usd=cost_usd,
            metadata={
                "letter_text": letter_text,
                "word_count": len(letter_text.split()),
                "overall_determination": overall,
                "coverage_amount_usd": coverage_usd,
            },
        )
