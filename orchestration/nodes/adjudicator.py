"""
Adjudicator node.

Makes the final coverage determination using all specialist findings.
Citation enforcement: every determination must reference at least one
PolicyFinding.clause_id. Unknown citations are logged as warnings.

Pre-adjudication refusal conditions (evaluated before LLM call):
- High-confidence fraud signals → escalate to human review (PARTIAL)
- 2+ critical consistency flags → escalate to human review (PARTIAL)
- No policy findings → FAILED (policy reasoner must have run)

Status: SUCCESS (determination produced),
        PARTIAL (human review required),
        FAILED (refusal non-escalation, or LLM error after retries).
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
from orchestration.state import AgentStatus, EvidenceStore
from orchestration.llmops.prompt_registry import register
from rag.generation.adjudicator_prompt import SYSTEM_PROMPT, build_adjudication_prompt
from rag.generation.refusal_logic import evaluate_refusal

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_MAX_PARSE_RETRIES = 2

_PROMPT_HASH = register("adjudicator_system", "v1", SYSTEM_PROMPT).hash


class _DeterminationItem(BaseModel):
    aspect: str
    determination: Literal["covered", "partial", "denied", "ambiguous"]
    cited_clause_ids: list[str] = Field(default_factory=list)
    rationale: str


class _AdjudicationResponse(BaseModel):
    overall_determination: Literal["covered", "partial", "denied", "human_review"]
    coverage_amount_usd: float = Field(ge=0.0, default=0.0)
    determinations: list[_DeterminationItem] = Field(default_factory=list)
    human_review_required: bool = False
    human_review_reason: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


class AdjudicatorNode(Node):
    """
    Final coverage determination with mandatory clause citation enforcement.

    Reads from EvidenceStore only — never from the ClaimPacket raw assets.
    Adjudicator blindness: the LLM sees structured findings, not images/PDFs.
    """

    @property
    def name(self) -> str:
        return "adjudicator"

    @property
    def timeout_s(self) -> float:
        return 90.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        refusal = evaluate_refusal(store)
        if refusal.should_refuse:
            logger.info("Adjudicator refusing: %s", refusal.reason)
            status = AgentStatus.PARTIAL if refusal.escalate_to_human else AgentStatus.FAILED
            return NodeResult(
                store=self._delta(store, status),
                status=status,
                metadata={
                    "refusal_reason": refusal.reason,
                    "escalate_to_human": refusal.escalate_to_human,
                    "prompt_hash": _PROMPT_HASH,
                    "model_used": _MODEL,
                },
            )

        prompt = build_adjudication_prompt(store)
        if degraded_context:
            notice_lines = "\n".join(f"- {v}" for v in degraded_context.values())
            prompt = f"Context notes from upstream failures:\n{notice_lines}\n\n{prompt}"

        parse_error: str | None = None
        adjudicated: _AdjudicationResponse | None = None
        cost_usd = 0.0

        for attempt in range(_MAX_PARSE_RETRIES + 1):
            full_prompt = (
                prompt
                if not parse_error
                else f"{prompt}\n\nPrevious parse error — return valid JSON: {parse_error}"
            )
            try:
                response = await litellm.acompletion(
                    model=_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": full_prompt},
                    ],
                    temperature=0.0,
                )
                try:
                    cost_usd += litellm.completion_cost(completion_response=response)
                except Exception:
                    pass

                raw = response.choices[0].message.content or ""
                adjudicated = _AdjudicationResponse.model_validate(
                    json.loads(_strip_fences(raw))
                )
                break
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt < _MAX_PARSE_RETRIES:
                    parse_error = str(e)
                    logger.warning(
                        "Adjudication parse error (attempt %d): %s", attempt + 1, e
                    )
                else:
                    logger.error("Adjudication failed after retries: %s", e)
                    return NodeResult(
                        store=self._delta(store, AgentStatus.FAILED),
                        status=AgentStatus.FAILED,
                        cost_usd=cost_usd,
                    )

        assert adjudicated is not None

        # Citation enforcement: warn on unknown clause citations
        all_cited = {cid for d in adjudicated.determinations for cid in d.cited_clause_ids}
        known_clauses = {f.clause_id for f in store.policy_findings}
        unknown = all_cited - known_clauses
        if unknown:
            logger.warning("Adjudicator cited clause_ids not in policy_findings: %s", unknown)

        status = (
            AgentStatus.PARTIAL if adjudicated.human_review_required else AgentStatus.SUCCESS
        )
        return NodeResult(
            store=self._delta(store, status),
            status=status,
            cost_usd=cost_usd,
            metadata={
                "overall_determination": adjudicated.overall_determination,
                "coverage_amount_usd": adjudicated.coverage_amount_usd,
                "confidence": adjudicated.confidence,
                "human_review_required": adjudicated.human_review_required,
                "human_review_reason": adjudicated.human_review_reason,
                "determinations": [d.model_dump() for d in adjudicated.determinations],
                "unknown_citations": sorted(unknown),
                "prompt_hash": _PROMPT_HASH,
                "model_used": _MODEL,
            },
        )
