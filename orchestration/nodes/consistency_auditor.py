"""
Consistency Auditor node.

Cross-checks all evidence findings for internal consistency and produces
ConsistencyFlags for downstream adjudication. Flags do not block the pipeline
but are passed to the Adjudicator which escalates on critical flags.

Status: SUCCESS (audit completed, even if no flags found),
        PARTIAL (LLM failed; no flags produced),
        SKIPPED (never — consistency audit always runs if store is non-empty).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Literal

import litellm
from pydantic import BaseModel, Field, ValidationError

from ingestion.models import ClaimPacket
from orchestration.nodes.base import Node, NodeResult
from orchestration.state import AgentStatus, ConsistencyFlag, EvidenceStore

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_MAX_PARSE_RETRIES = 2

_CONSISTENCY_PROMPT = """\
{degraded_notice}\
You are an insurance consistency auditor. Cross-check all evidence for conflicts.

CLAIM ID: {claim_id}

DAMAGE FINDINGS:
{damage_summary}

DOCUMENT FINDINGS:
{document_summary}

STATEMENT FINDINGS:
{statement_summary}

Check for:
- date_mismatch: genuine date conflicts between documents or between a document and an explicitly stated incident date.
  IMPORTANT date_mismatch rules:
  · Repair estimates, invoices, and damage assessments are routinely dated DAYS TO MONTHS after the incident — this is normal processing time and must NOT be flagged.
  · Only flag when a document is definitively dated BEFORE the stated incident date (e.g., a repair invoice issued before the incident happened is suspicious; a repair invoice issued after is expected).
  · When the claim form lists no explicit incident date, do NOT infer the incident date from a date mentioned in a recorded statement or audio transcript — that reference may be approximate or contextual. Only flag if at least two independent documents provide conflicting explicit dates for the same event.
- damage_narrative_conflict: physical damage findings directly contradict the claimant's description of the incident mechanism (not a date issue — a physical inconsistency).
- estimate_conflict: repair cost estimates that are grossly disproportionate to the assessed damage severity category (e.g., a minor cosmetic scratch with a $15,000 estimate).
- coverage_gap: damage categories that clearly fall outside the policy coverage type claimed.
- document_inconsistency: conflicting field values for the same fact across different documents (e.g., two documents show different VIN numbers, different policy holder names).

For each conflict found:
- flag_type: one of the categories above
- description: specifically what conflicts and why it is an inconsistency
- severity: "minor" (informational), "major" (needs explanation), "critical" (blocks adjudication)
- involved_findings: list of field_names, region_ids, or claim excerpts involved

Return an empty list if no conflicts are found.
Respond with valid JSON only, no markdown fences:
{{
  "flags": [
    {{
      "flag_type": "...",
      "description": "...",
      "severity": "minor|major|critical",
      "involved_findings": []
    }}
  ]
}}"""


class _ConsistencyFlagRaw(BaseModel):
    flag_type: str
    description: str
    severity: Literal["minor", "major", "critical"]
    involved_findings: list[str] = Field(default_factory=list)


class _ConsistencyAuditResponse(BaseModel):
    flags: list[_ConsistencyFlagRaw]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


class ConsistencyAuditorNode(Node):
    """
    Audits cross-modal evidence consistency. Produces ConsistencyFlags that
    influence adjudicator confidence and can trigger human review escalation.
    """

    @property
    def name(self) -> str:
        return "consistency_auditor"

    @property
    def timeout_s(self) -> float:
        return 60.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        damage_summary = (
            "\n".join(
                f"  - {f.region_id}: {f.category}, ~${f.estimated_cost_usd:.0f}"
                f", {f.description[:80]}"
                for f in store.damage_findings
            )
            or "  None"
        )
        doc_summary = (
            "\n".join(f"  - {f.field_name}: {f.value}" for f in store.document_findings)
            or "  None"
        )
        stmt_summary = (
            "\n".join(f'  - "{f.claim[:100]}"' for f in store.statement_findings)
            or "  None"
        )
        degraded_notice = ""
        if degraded_context:
            lines = "\n".join(f"- {v}" for v in degraded_context.values())
            degraded_notice = f"Context notes:\n{lines}\n\n"

        prompt = _CONSISTENCY_PROMPT.format(
            degraded_notice=degraded_notice,
            claim_id=store.claim_id,
            damage_summary=damage_summary,
            document_summary=doc_summary,
            statement_summary=stmt_summary,
        )

        parse_error: str | None = None
        audited: _ConsistencyAuditResponse | None = None
        cost_usd = 0.0
        llm_failed = False

        for attempt in range(_MAX_PARSE_RETRIES + 1):
            full_prompt = (
                prompt
                if not parse_error
                else f"{prompt}\n\nPrevious parse error — return valid JSON: {parse_error}"
            )
            try:
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
                audited = _ConsistencyAuditResponse.model_validate(
                    json.loads(_strip_fences(raw))
                )
                break
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt < _MAX_PARSE_RETRIES:
                    parse_error = str(e)
                    logger.warning(
                        "Consistency audit parse error (attempt %d): %s", attempt + 1, e
                    )
                else:
                    logger.error("Consistency audit failed after retries: %s", e)
                    llm_failed = True
                    audited = _ConsistencyAuditResponse(flags=[])
            except Exception as e:
                logger.error("Consistency LLM call failed: %s", e)
                llm_failed = True
                audited = _ConsistencyAuditResponse(flags=[])
                break

        assert audited is not None
        flags = [
            ConsistencyFlag(
                flag_type=f.flag_type,
                description=f.description,
                severity=f.severity,
                involved_findings=f.involved_findings,
            )
            for f in audited.flags
        ]

        status = AgentStatus.PARTIAL if llm_failed else AgentStatus.SUCCESS
        return NodeResult(
            store=self._delta(store, status, consistency_flags=flags),
            status=status,
            cost_usd=cost_usd,
        )
