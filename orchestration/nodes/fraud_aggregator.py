"""
Fraud Aggregator node.

Two-pass approach:
  1. Rule-based feature extraction over damage/document findings (fast, deterministic)
  2. LLM soft-signal analysis over all evidence (slower, catches narrative patterns)

Rule signals are always produced; LLM signals degrade to an empty list on failure.

Status: SUCCESS (LLM analysis completed),
        PARTIAL (LLM failed but rule signals available or no evidence to analyze),
        FAILED (rare — rule pass never fails, so FAILED only if unexpected crash).
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
from orchestration.state import AgentStatus, EvidenceStore, FraudSignal

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_MAX_PARSE_RETRIES = 2

_FRAUD_PROMPT = """\
{degraded_notice}\
You are an insurance fraud analyst. Review the evidence and identify potential fraud signals.

CLAIM ID: {claim_id}
DESCRIPTION: {description}

DAMAGE FINDINGS:
{damage_summary}

DOCUMENT FINDINGS:
{document_summary}

STATEMENT FINDINGS:
{statement_summary}

Identify fraud indicators from these categories:
- staged_damage: damage patterns inconsistent with stated cause of loss
- velocity_anomaly: unusually high frequency or rapid sequence of claims
- narrative_inconsistency: mismatches between statements and physical evidence
- document_fraud: signs of document alteration or fabrication
- prior_loss_concealment: evidence of undisclosed prior damage
- inflated_estimate: repair estimates inconsistent with stated damage severity

For each signal found:
- signal_type: one of the categories above
- description: what specifically triggered this signal
- severity: "low", "medium", or "high"
- confidence: 0.0–1.0
- source: always "llm_soft_signal"

Return an empty list if no signals are found.
Respond with valid JSON only, no markdown fences:
{{
  "signals": [
    {{
      "signal_type": "...",
      "description": "...",
      "severity": "low|medium|high",
      "confidence": 0.0,
      "source": "llm_soft_signal"
    }}
  ]
}}"""


class _FraudSignalRaw(BaseModel):
    signal_type: str
    description: str
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["tabular_model", "llm_soft_signal", "rule"] = "llm_soft_signal"


class _FraudAnalysisResponse(BaseModel):
    signals: list[_FraudSignalRaw]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


def _rule_based_signals(store: EvidenceStore) -> list[FraudSignal]:
    signals: list[FraudSignal] = []

    # Total loss alongside exclusively cosmetic surrounding damage
    categories = [f.category for f in store.damage_findings]
    if "total_loss" in categories and len(categories) > 1:
        non_total = [c for c in categories if c != "total_loss"]
        if all(c == "cosmetic" for c in non_total):
            signals.append(
                FraudSignal(
                    signal_type="staged_damage",
                    description=(
                        "Total loss declared alongside exclusively cosmetic "
                        "surrounding damage — inconsistent pattern"
                    ),
                    severity="medium",
                    confidence=0.7,
                    source="rule",
                )
            )

    # Severe category but suspiciously low estimate
    for f in store.damage_findings:
        if f.category == "severe" and f.estimated_cost_usd < 500:
            signals.append(
                FraudSignal(
                    signal_type="inflated_estimate",
                    description=(
                        f"Region {f.region_id!r} categorized as 'severe' but "
                        f"estimated at only ${f.estimated_cost_usd:.0f}"
                    ),
                    severity="low",
                    confidence=0.6,
                    source="rule",
                )
            )

    return signals


class FraudAggregatorNode(Node):
    """
    Runs rule-based fraud detection and LLM soft-signal analysis over all evidence.
    """

    @property
    def name(self) -> str:
        return "fraud_aggregator"

    @property
    def timeout_s(self) -> float:
        return 60.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        rule_signals = _rule_based_signals(store)

        damage_summary = (
            "\n".join(
                f"  - {f.region_id}: {f.category}, ~${f.estimated_cost_usd:.0f}"
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

        prompt = _FRAUD_PROMPT.format(
            degraded_notice=degraded_notice,
            claim_id=store.claim_id,
            description=str(packet.form_data.get("description", "No description")),
            damage_summary=damage_summary,
            document_summary=doc_summary,
            statement_summary=stmt_summary,
        )

        parse_error: str | None = None
        analyzed: _FraudAnalysisResponse | None = None
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
                analyzed = _FraudAnalysisResponse.model_validate(
                    json.loads(_strip_fences(raw))
                )
                break
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt < _MAX_PARSE_RETRIES:
                    parse_error = str(e)
                    logger.warning(
                        "Fraud analysis parse error (attempt %d): %s", attempt + 1, e
                    )
                else:
                    logger.error("Fraud analysis failed after retries: %s", e)
                    llm_failed = True
                    analyzed = _FraudAnalysisResponse(signals=[])
            except Exception as e:
                logger.error("Fraud LLM call failed: %s", e)
                llm_failed = True
                analyzed = _FraudAnalysisResponse(signals=[])
                break

        assert analyzed is not None
        llm_signals = [
            FraudSignal(
                signal_type=s.signal_type,
                description=s.description,
                severity=s.severity,
                confidence=s.confidence,
                source=s.source,
            )
            for s in analyzed.signals
        ]

        all_signals = rule_signals + llm_signals
        status = AgentStatus.PARTIAL if llm_failed else AgentStatus.SUCCESS
        return NodeResult(
            store=self._delta(store, status, fraud_signals=all_signals),
            status=status,
            cost_usd=cost_usd,
        )
