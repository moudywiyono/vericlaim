"""
Prompt templates for the Adjudicator node.

Kept separate so the adjudicator_node.py stays focused on orchestration logic and
prompt engineering can be iterated without touching node code.
"""
from __future__ import annotations

from orchestration.state import EvidenceStore

SYSTEM_PROMPT = """\
You are an insurance claims adjudicator at VeriClaim Mutual Insurance Company.

Your role is to make a final coverage determination based strictly on the policy \
findings provided. You must cite specific policy clause_ids for every determination.

Rules:
1. Every determination must reference at least one policy clause_id from the findings.
2. You may not infer coverage beyond what the policy findings explicitly state.
3. If evidence is contradictory, acknowledge it and apply the most conservative reading.
4. If high-severity fraud signals are present, set human_review_required=true.
5. Your output must be valid JSON — no prose, no markdown fences."""

_ADJUDICATION_TEMPLATE = """\
Review the evidence below and provide a final coverage determination.

POLICY FINDINGS (from Policy Reasoner — cite these clause_ids):
{policy_findings}

DAMAGE FINDINGS:
{damage_findings}

DOCUMENT FINDINGS:
{document_findings}

STATEMENT FINDINGS:
{statement_findings}

FRAUD SIGNALS:
{fraud_signals}

CONSISTENCY FLAGS:
{consistency_flags}

Provide your adjudication in this exact JSON structure:
{{
  "overall_determination": "covered|partial|denied|human_review",
  "coverage_amount_usd": 0.0,
  "determinations": [
    {{
      "aspect": "what coverage aspect is being determined",
      "determination": "covered|partial|denied|ambiguous",
      "cited_clause_ids": ["CLAUSE_ID"],
      "rationale": "brief explanation citing the specific policy language"
    }}
  ],
  "human_review_required": false,
  "human_review_reason": "",
  "confidence": 0.0
}}"""


def _fmt_list(items: list, fmt_fn) -> str:  # type: ignore[type-arg]
    if not items:
        return "  None"
    return "\n".join(f"  - {fmt_fn(item)}" for item in items)


def build_adjudication_prompt(store: EvidenceStore) -> str:
    policy_str = _fmt_list(
        store.policy_findings,
        lambda f: (
            f"{f.clause_id} [{f.corpus_layer}]: {f.determination}"
            f" — \"{f.cited_text[:120].rstrip()}...\""
            + (f" | endorsements: {f.endorsements_applied}" if f.endorsements_applied else "")
        ),
    )
    damage_str = _fmt_list(
        store.damage_findings,
        lambda f: (
            f"{f.region_id}: {f.category}"
            f", ~${f.estimated_cost_usd:.0f}"
            f" (conf={f.cost_confidence:.0%}) — {f.description[:80]}"
        ),
    )
    doc_str = _fmt_list(
        store.document_findings,
        lambda f: f"{f.field_name}: {f.value}",
    )
    stmt_str = _fmt_list(
        store.statement_findings,
        lambda f: f'"{f.claim[:100]}"',
    )
    fraud_str = _fmt_list(
        store.fraud_signals,
        lambda f: (
            f"{f.signal_type} [{f.severity}] conf={f.confidence:.0%}"
            f" ({f.source}): {f.description[:80]}"
        ),
    )
    consistency_str = _fmt_list(
        store.consistency_flags,
        lambda f: f"{f.flag_type} [{f.severity}]: {f.description[:80]}",
    )

    return _ADJUDICATION_TEMPLATE.format(
        policy_findings=policy_str,
        damage_findings=damage_str,
        document_findings=doc_str,
        statement_findings=stmt_str,
        fraud_signals=fraud_str,
        consistency_flags=consistency_str,
    )
