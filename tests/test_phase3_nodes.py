"""
Tests for Phase 3 orchestration nodes.

All LLM calls are mocked — no API key required.
Retriever is injected to avoid model downloads.

Coverage:
- PolicyReasonerNode: success, empty retrieval, LLM parse error, retriever failure
- StatementAnalystNode: description fallback, audio skip, LLM success
- FraudAggregatorNode: rule signals, LLM success, LLM failure degradation
- ConsistencyAuditorNode: no flags, flags produced, LLM failure degradation
- AdjudicatorNode: refusal (no findings), refusal (fraud), success, human review
- OutputDrafterNode: success, LLM failure
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.models import ClaimPacket, ClaimType
from orchestration.nodes.adjudicator import AdjudicatorNode
from orchestration.nodes.consistency_auditor import ConsistencyAuditorNode
from orchestration.nodes.fraud_aggregator import FraudAggregatorNode
from orchestration.nodes.output_drafter import OutputDrafterNode
from orchestration.nodes.policy_reasoner import PolicyReasonerNode
from orchestration.nodes.statement_analyst import StatementAnalystNode
from orchestration.state import (
    AgentStatus,
    ConsistencyFlag,
    DamageFinding,
    DocumentFinding,
    EvidenceStore,
    FraudSignal,
    PolicyFinding,
    StatementFinding,
)
from rag.ingestion.chunker import PolicyChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_packet(
    claim_id: str = "CLM-001",
    description: str = "rear-end collision at intersection",
    audio: list[Path] | None = None,
) -> ClaimPacket:
    return ClaimPacket(
        claim_id=claim_id,
        claim_dir=Path("/tmp"),
        claim_type=ClaimType.AUTO,
        form_data={"description": description},
        audio=audio or [],
    )


def _make_store(
    claim_id: str = "CLM-001",
    damage: bool = False,
    policy: bool = False,
    fraud: bool = False,
    flags: bool = False,
) -> EvidenceStore:
    return EvidenceStore(
        claim_id=claim_id,
        damage_findings=(
            [
                DamageFinding(
                    region_id="front_bumper",
                    category="moderate",
                    description="Crumpled front bumper",
                    estimated_cost_usd=2500.0,
                    cost_confidence=0.8,
                    evidence_uri="file:///img.jpg",
                )
            ]
            if damage
            else []
        ),
        policy_findings=(
            [
                PolicyFinding(
                    clause_id="PART_D.1",
                    corpus_layer="policy",
                    determination="covered",
                    cited_text="We will pay for direct and accidental loss",
                    confidence=0.9,
                )
            ]
            if policy
            else []
        ),
        fraud_signals=(
            [
                FraudSignal(
                    signal_type="staged_damage",
                    description="test",
                    severity="high",
                    confidence=0.9,
                    source="rule",
                )
            ]
            if fraud
            else []
        ),
        consistency_flags=(
            [
                ConsistencyFlag(
                    flag_type="date_mismatch",
                    description="conflict",
                    severity="critical",
                ),
                ConsistencyFlag(
                    flag_type="estimate_conflict",
                    description="conflict 2",
                    severity="critical",
                ),
            ]
            if flags
            else []
        ),
    )


def _make_chunk(clause_id: str, text: str) -> PolicyChunk:
    return PolicyChunk(
        chunk_id=f"policy:{clause_id}",
        corpus="policy",
        clause_id=clause_id,
        path=["Part D"],
        text=text,
        parent_summary="Part D",
        cross_refs=[],
        definitions_appended=[],
    )


def _mock_litellm(content: str):
    """Return a mock litellm.acompletion that yields a response with given content."""
    resp = MagicMock()
    resp.choices[0].message.content = content
    mock = AsyncMock(return_value=resp)
    return mock


# ---------------------------------------------------------------------------
# PolicyReasonerNode
# ---------------------------------------------------------------------------

class TestPolicyReasonerNode:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        chunk = _make_chunk(
            "PART_D.1",
            "We will pay for direct and accidental loss to your covered auto.",
        )
        mock_retriever = AsyncMock()
        mock_retriever.retrieve.return_value = [(chunk, 0.9)]

        response_json = json.dumps({
            "findings": [
                {
                    "clause_id": "PART_D.1",
                    "corpus_layer": "policy",
                    "determination": "covered",
                    "cited_text": "We will pay for direct and accidental loss",
                    "confidence": 0.9,
                    "endorsements_applied": [],
                }
            ]
        })

        node = PolicyReasonerNode(retriever=mock_retriever)
        packet = _make_packet()
        store = _make_store()

        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(store, packet)

        assert result.status == AgentStatus.SUCCESS
        assert len(result.store.policy_findings) == 1
        assert result.store.policy_findings[0].clause_id == "PART_D.1"

    @pytest.mark.asyncio
    async def test_empty_retrieval_returns_partial(self) -> None:
        mock_retriever = AsyncMock()
        mock_retriever.retrieve.return_value = []

        node = PolicyReasonerNode(retriever=mock_retriever)
        result = await node.run(_make_store(), _make_packet())
        assert result.status == AgentStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_retriever_failure_returns_failed(self) -> None:
        mock_retriever = AsyncMock()
        mock_retriever.retrieve.side_effect = RuntimeError("index error")

        node = PolicyReasonerNode(retriever=mock_retriever)
        result = await node.run(_make_store(), _make_packet())
        assert result.status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_invalid_json_retries_and_fails(self) -> None:
        chunk = _make_chunk("PART_D.1", "We will pay for loss.")
        mock_retriever = AsyncMock()
        mock_retriever.retrieve.return_value = [(chunk, 0.9)]

        node = PolicyReasonerNode(retriever=mock_retriever)
        with patch("litellm.acompletion", _mock_litellm("not json at all")):
            result = await node.run(_make_store(), _make_packet())
        assert result.status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_unknown_corpus_layer_filtered(self) -> None:
        chunk = _make_chunk("PART_D.1", "We will pay for loss.")
        mock_retriever = AsyncMock()
        mock_retriever.retrieve.return_value = [(chunk, 0.9)]

        response_json = json.dumps({
            "findings": [
                {
                    "clause_id": "PART_D.1",
                    "corpus_layer": "unknown_layer",
                    "determination": "covered",
                    "cited_text": "We will pay",
                    "confidence": 0.8,
                    "endorsements_applied": [],
                }
            ]
        })

        node = PolicyReasonerNode(retriever=mock_retriever)
        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(_make_store(), _make_packet())
        # Invalid layer filtered out → PARTIAL (no valid findings)
        assert len(result.store.policy_findings) == 0


# ---------------------------------------------------------------------------
# StatementAnalystNode
# ---------------------------------------------------------------------------

class TestStatementAnalystNode:
    @pytest.mark.asyncio
    async def test_skipped_without_audio_or_description(self) -> None:
        node = StatementAnalystNode()
        packet = _make_packet(description="")
        result = await node.run(_make_store(), packet)
        assert result.status == AgentStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_uses_description_fallback(self) -> None:
        response_json = json.dumps({
            "findings": [
                {
                    "claim": "Car was rear-ended at a red light",
                    "timestamp_in_audio": 0.0,
                    "speaker_confidence": 0.9,
                    "cross_refs": [],
                }
            ]
        })

        node = StatementAnalystNode()
        packet = _make_packet(description="car was rear-ended at a red light")

        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(_make_store(), packet)

        assert result.status == AgentStatus.SUCCESS
        assert len(result.store.statement_findings) == 1

    @pytest.mark.asyncio
    async def test_llm_failure_returns_failed(self) -> None:
        node = StatementAnalystNode()
        packet = _make_packet(description="some description")

        with patch("litellm.acompletion", side_effect=Exception("API error")):
            result = await node.run(_make_store(), packet)

        assert result.status == AgentStatus.FAILED


# ---------------------------------------------------------------------------
# FraudAggregatorNode
# ---------------------------------------------------------------------------

class TestFraudAggregatorNode:
    @pytest.mark.asyncio
    async def test_rule_signals_on_total_loss_with_cosmetic(self) -> None:
        store = EvidenceStore(
            claim_id="CLM-001",
            damage_findings=[
                DamageFinding(
                    region_id="engine",
                    category="total_loss",
                    description="total loss",
                    estimated_cost_usd=20000.0,
                    cost_confidence=0.9,
                    evidence_uri="file:///img.jpg",
                ),
                DamageFinding(
                    region_id="door_handle",
                    category="cosmetic",
                    description="scratch",
                    estimated_cost_usd=100.0,
                    cost_confidence=0.9,
                    evidence_uri="file:///img2.jpg",
                ),
            ],
        )

        response_json = json.dumps({"signals": []})
        node = FraudAggregatorNode()

        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(store, _make_packet())

        # Rule should have fired
        rule_signals = [s for s in result.store.fraud_signals if s.source == "rule"]
        assert len(rule_signals) >= 1
        assert rule_signals[0].signal_type == "staged_damage"

    @pytest.mark.asyncio
    async def test_llm_signals_added(self) -> None:
        response_json = json.dumps({
            "signals": [
                {
                    "signal_type": "narrative_inconsistency",
                    "description": "Statement conflicts with damage pattern",
                    "severity": "medium",
                    "confidence": 0.7,
                    "source": "llm_soft_signal",
                }
            ]
        })

        node = FraudAggregatorNode()
        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(_make_store(damage=True), _make_packet())

        llm_signals = [s for s in result.store.fraud_signals if s.source == "llm_soft_signal"]
        assert len(llm_signals) == 1

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_to_partial(self) -> None:
        node = FraudAggregatorNode()
        with patch("litellm.acompletion", side_effect=Exception("error")):
            result = await node.run(_make_store(), _make_packet())
        assert result.status == AgentStatus.PARTIAL


# ---------------------------------------------------------------------------
# ConsistencyAuditorNode
# ---------------------------------------------------------------------------

class TestConsistencyAuditorNode:
    @pytest.mark.asyncio
    async def test_no_flags_returns_success(self) -> None:
        response_json = json.dumps({"flags": []})
        node = ConsistencyAuditorNode()

        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(_make_store(damage=True), _make_packet())

        assert result.status == AgentStatus.SUCCESS
        assert result.store.consistency_flags == []

    @pytest.mark.asyncio
    async def test_flags_added_to_store(self) -> None:
        response_json = json.dumps({
            "flags": [
                {
                    "flag_type": "date_mismatch",
                    "description": "Loss date in form differs from police report",
                    "severity": "major",
                    "involved_findings": ["date_of_loss"],
                }
            ]
        })
        node = ConsistencyAuditorNode()

        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(_make_store(damage=True), _make_packet())

        assert len(result.store.consistency_flags) == 1
        assert result.store.consistency_flags[0].flag_type == "date_mismatch"

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_to_partial(self) -> None:
        node = ConsistencyAuditorNode()
        with patch("litellm.acompletion", side_effect=Exception("error")):
            result = await node.run(_make_store(), _make_packet())
        assert result.status == AgentStatus.PARTIAL


# ---------------------------------------------------------------------------
# AdjudicatorNode
# ---------------------------------------------------------------------------

class TestAdjudicatorNode:
    @pytest.mark.asyncio
    async def test_refuses_without_policy_findings(self) -> None:
        node = AdjudicatorNode()
        result = await node.run(_make_store(), _make_packet())
        assert result.status == AgentStatus.FAILED
        assert "refusal_reason" in result.metadata

    @pytest.mark.asyncio
    async def test_escalates_on_high_fraud(self) -> None:
        node = AdjudicatorNode()
        store = _make_store(policy=True, fraud=True)
        result = await node.run(store, _make_packet())
        assert result.status == AgentStatus.PARTIAL
        assert result.metadata.get("escalate_to_human") is True

    @pytest.mark.asyncio
    async def test_escalates_on_critical_flags(self) -> None:
        node = AdjudicatorNode()
        store = _make_store(policy=True, flags=True)
        result = await node.run(store, _make_packet())
        assert result.status == AgentStatus.PARTIAL
        assert result.metadata.get("escalate_to_human") is True

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        response_json = json.dumps({
            "overall_determination": "covered",
            "coverage_amount_usd": 2500.0,
            "determinations": [
                {
                    "aspect": "front bumper collision damage",
                    "determination": "covered",
                    "cited_clause_ids": ["PART_D.1"],
                    "rationale": "Collision is a covered peril under PART D.",
                }
            ],
            "human_review_required": False,
            "human_review_reason": "",
            "confidence": 0.92,
        })

        node = AdjudicatorNode()
        store = _make_store(policy=True, damage=True)

        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(store, _make_packet())

        assert result.status == AgentStatus.SUCCESS
        assert result.metadata["overall_determination"] == "covered"
        assert result.metadata["coverage_amount_usd"] == pytest.approx(2500.0)

    @pytest.mark.asyncio
    async def test_human_review_returns_partial(self) -> None:
        response_json = json.dumps({
            "overall_determination": "human_review",
            "coverage_amount_usd": 0.0,
            "determinations": [],
            "human_review_required": True,
            "human_review_reason": "Complex coverage question",
            "confidence": 0.4,
        })

        node = AdjudicatorNode()
        store = _make_store(policy=True)

        with patch("litellm.acompletion", _mock_litellm(response_json)):
            result = await node.run(store, _make_packet())

        assert result.status == AgentStatus.PARTIAL
        assert result.metadata["human_review_required"] is True


# ---------------------------------------------------------------------------
# OutputDrafterNode
# ---------------------------------------------------------------------------

class TestOutputDrafterNode:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        letter = (
            "Dear Claimant,\n\nWe have reviewed your claim CLM-001. "
            "Based on our review, your claim is COVERED.\n\n"
            "This determination is made pursuant to the terms and conditions of your policy.\n"
            "You have the right to appeal this decision within 30 days of this letter."
        )
        node = OutputDrafterNode()
        store = _make_store(policy=True, damage=True)

        with patch("litellm.acompletion", _mock_litellm(letter)):
            result = await node.run(store, _make_packet())

        assert result.status == AgentStatus.SUCCESS
        assert "letter_text" in result.metadata
        assert len(result.metadata["letter_text"]) > 0
        assert result.metadata["word_count"] > 5

    @pytest.mark.asyncio
    async def test_llm_failure_returns_failed(self) -> None:
        node = OutputDrafterNode()
        with patch("litellm.acompletion", side_effect=Exception("API down")):
            result = await node.run(_make_store(policy=True), _make_packet())
        assert result.status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_denied_claim_letter(self) -> None:
        letter = "Dear Claimant, Your claim is DENIED. Appeal within 30 days."
        node = OutputDrafterNode()
        # Empty policy findings → denial
        store = _make_store()

        with patch("litellm.acompletion", _mock_litellm(letter)):
            result = await node.run(store, _make_packet())

        assert result.status == AgentStatus.SUCCESS
        assert result.metadata["overall_determination"] == "denied"
