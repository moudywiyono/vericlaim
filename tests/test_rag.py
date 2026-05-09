"""
Tests for the Phase 3 RAG layer.

Coverage:
- chunker: parse_corpus_file, cross-ref extraction, definition injection
- BM25Index: build, search, save/load
- DenseIndex: build (mocked), search (mocked)
- RRF fusion: correctness, empty inputs
- CrossEncoderReranker: pass-through on unavailable model
- QueryDecomposer: fallback on LLM failure
- HyDE: abstract gate, LLM failure fallback
- RetrievalOrchestrator: injected layers (no model downloads)
- citation_validator: all three layers
- refusal_logic: all escalation conditions
- endorsement_linker: map building and coverage check
- rag_metrics: recall@k, MRR, endorsement_attachment_rate, faithfulness
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.ingestion.chunker import PolicyChunk, _extract_cross_refs, parse_corpus_file
from rag.ingestion.endorsement_linker import (
    build_endorsement_map,
    endorsement_coverage,
)
from rag.indexing.sparse_indexer import BM25Index
from rag.retrieval.hybrid import reciprocal_rank_fusion
from rag.retrieval.reranker import CrossEncoderReranker
from rag.generation.citation_validator import (
    CitationLayer,
    validate_citation,
    validate_all_citations,
    citation_pass_rate,
)
from rag.generation.refusal_logic import evaluate_refusal
from evals.metrics.rag_metrics import (
    endorsement_attachment_rate,
    faithfulness_score,
    mean_reciprocal_rank,
    recall_at_k,
)
from orchestration.state import (
    ConsistencyFlag,
    EvidenceStore,
    FraudSignal,
    PolicyFinding,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chunk(
    clause_id: str,
    text: str,
    corpus: Literal["policy", "endorsement", "regulation", "guideline"] = "policy",
    modifies: str | None = None,
) -> PolicyChunk:
    return PolicyChunk(
        chunk_id=f"{corpus}:{clause_id}",
        corpus=corpus,
        clause_id=clause_id,
        path=["Test Section"],
        text=text,
        parent_summary="Test Section",
        cross_refs=[],
        definitions_appended=[],
        modifies=modifies,
    )


def _make_store(
    claim_id: str = "CLM-001",
    policy_findings: list | None = None,
    fraud_signals: list | None = None,
    consistency_flags: list | None = None,
) -> EvidenceStore:
    return EvidenceStore(
        claim_id=claim_id,
        policy_findings=policy_findings or [],
        fraud_signals=fraud_signals or [],
        consistency_flags=consistency_flags or [],
    )


CORPUS_TEXT = """\
CLAUSE_ID: PART_D.1
SECTION: Part D - Physical Damage Coverage
SUBSECTION: Coverage Grant

We will pay for direct and accidental loss to your covered auto. Collision means \
the upset of your covered auto or their impact with another vehicle or object.

CLAUSE_ID: PART_D.3
SECTION: Part D - Physical Damage Coverage
SUBSECTION: Exclusions

We do not cover loss to custom parts or equipment unless Endorsement VC-004 applies. \
This exclusion applies to aftermarket audio equipment not in original factory location.
"""


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

class TestChunker:
    def test_parse_corpus_file(self, tmp_path: Path) -> None:
        corpus_file = tmp_path / "policy.txt"
        corpus_file.write_text(CORPUS_TEXT)
        chunks = parse_corpus_file(corpus_file, "policy")
        assert len(chunks) == 2
        assert chunks[0].clause_id == "PART_D.1"
        assert chunks[1].clause_id == "PART_D.3"

    def test_chunk_ids_are_prefixed(self, tmp_path: Path) -> None:
        corpus_file = tmp_path / "policy.txt"
        corpus_file.write_text(CORPUS_TEXT)
        chunks = parse_corpus_file(corpus_file, "policy")
        assert all(c.chunk_id.startswith("policy:") for c in chunks)

    def test_path_breadcrumb(self, tmp_path: Path) -> None:
        corpus_file = tmp_path / "policy.txt"
        corpus_file.write_text(CORPUS_TEXT)
        chunks = parse_corpus_file(corpus_file, "policy")
        assert "Part D - Physical Damage Coverage" in chunks[0].path

    def test_definition_injection(self, tmp_path: Path) -> None:
        corpus_file = tmp_path / "policy.txt"
        corpus_file.write_text(CORPUS_TEXT)
        chunks = parse_corpus_file(corpus_file, "policy")
        # First chunk mentions "collision" and "covered auto" — definitions should be appended
        first = chunks[0]
        assert "collision" in first.definitions_appended or "covered auto" in first.definitions_appended
        assert "[Definitions for terms used above]" in first.text

    def test_cross_ref_extraction(self) -> None:
        refs = _extract_cross_refs("See PART D for collision coverage. Endorsement VC-004 applies.", "PART_A.1")
        assert "PART_D" in refs or any("PART_D" in r for r in refs)

    def test_empty_body_skipped(self, tmp_path: Path) -> None:
        text = "CLAUSE_ID: PART_A.1\nSECTION: Test\n\n"
        corpus_file = tmp_path / "policy.txt"
        corpus_file.write_text(text)
        chunks = parse_corpus_file(corpus_file, "policy")
        assert len(chunks) == 0


# ---------------------------------------------------------------------------
# BM25Index tests
# ---------------------------------------------------------------------------

class TestBM25Index:
    def test_build_and_search(self) -> None:
        chunks = [
            _make_chunk("C1", "collision damage to front bumper repair"),
            _make_chunk("C2", "theft exclusion does not cover stolen vehicles"),
            _make_chunk("C3", "rental reimbursement up to fifty dollars per day"),
        ]
        idx = BM25Index()
        idx.build(chunks)
        results = idx.search("collision front bumper", k=2)
        assert len(results) <= 2
        assert results[0][0].clause_id == "C1"

    def test_search_empty_index(self) -> None:
        idx = BM25Index()
        assert idx.search("anything") == []

    def test_zero_score_filtered(self) -> None:
        chunks = [_make_chunk("C1", "collision damage repair")]
        idx = BM25Index()
        idx.build(chunks)
        results = idx.search("unrelated term xyz")
        assert results == []

    def test_size_property(self) -> None:
        chunks = [_make_chunk(f"C{i}", f"text {i}") for i in range(5)]
        idx = BM25Index()
        idx.build(chunks)
        assert idx.size == 5

    def test_save_load(self, tmp_path: Path) -> None:
        # BM25Okapi IDF = log((N-df+0.5)/(df+0.5)); with N=2,df=1 → IDF=0.
        # Need ≥3 docs so unique terms get IDF = log(2.5/1.5) > 0.
        chunks = [
            _make_chunk("C1", "collision damage front bumper repair"),
            _make_chunk("C2", "theft exclusion vehicle not covered"),
            _make_chunk("C3", "rental reimbursement fifty dollars per day"),
        ]
        idx = BM25Index()
        idx.build(chunks)
        path = tmp_path / "bm25.pkl"
        idx.save(path)
        loaded = BM25Index.load(path)
        assert loaded.size == 3
        results = loaded.search("collision damage", k=1)
        assert len(results) == 1
        assert results[0][0].clause_id == "C1"


# ---------------------------------------------------------------------------
# RRF fusion tests
# ---------------------------------------------------------------------------

class TestRRF:
    def test_single_list(self) -> None:
        c1, c2 = _make_chunk("C1", "a"), _make_chunk("C2", "b")
        ranked = [(c1, 0.9), (c2, 0.5)]
        fused = reciprocal_rank_fusion([ranked])
        assert fused[0][0].chunk_id == "policy:C1"

    def test_two_lists_consensus(self) -> None:
        c1, c2, c3 = _make_chunk("C1", "a"), _make_chunk("C2", "b"), _make_chunk("C3", "c")
        list1 = [(c1, 0.9), (c2, 0.8), (c3, 0.7)]
        list2 = [(c1, 0.95), (c3, 0.85), (c2, 0.6)]
        fused = reciprocal_rank_fusion([list1, list2])
        # C1 is rank-1 in both lists → highest RRF score
        assert fused[0][0].chunk_id == "policy:C1"

    def test_empty_input(self) -> None:
        assert reciprocal_rank_fusion([]) == []

    def test_scores_decreasing(self) -> None:
        chunks = [_make_chunk(f"C{i}", f"text {i}") for i in range(5)]
        ranked = [(c, 1.0 - i * 0.1) for i, c in enumerate(chunks)]
        fused = reciprocal_rank_fusion([ranked])
        scores = [s for _, s in fused]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# CrossEncoderReranker tests
# ---------------------------------------------------------------------------

class TestCrossEncoderReranker:
    def test_pass_through_on_unavailable(self) -> None:
        reranker = CrossEncoderReranker("nonexistent-model-xyz")
        # Force unavailable without needing sentence_transformers installed
        reranker._available = False
        chunks = [
            (_make_chunk("C1", "text"), 0.9),
            (_make_chunk("C2", "text"), 0.8),
        ]
        result = reranker.rerank("query", chunks, top_k=2)
        assert len(result) == 2

    def test_top_k_respected_on_passthrough(self) -> None:
        reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)
        reranker._model = None
        reranker._available = False
        reranker._model_name = "test"
        chunks = [(_make_chunk(f"C{i}", "t"), float(i)) for i in range(5)]
        result = reranker.rerank("q", chunks, top_k=3)
        assert len(result) == 3

    def test_empty_candidates(self) -> None:
        reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)
        reranker._model = None
        reranker._available = False
        reranker._model_name = "test"
        assert reranker.rerank("q", []) == []


# ---------------------------------------------------------------------------
# RetrievalOrchestrator tests (injected layers, no model downloads)
# ---------------------------------------------------------------------------

class TestRetrievalOrchestrator:
    def test_retrieve_with_mocked_layers(self) -> None:
        from rag.retrieval.orchestrator import CorpusLayer, RetrievalConfig, RetrievalOrchestrator

        chunk = _make_chunk("PART_D.1", "collision coverage we will pay")
        bm25 = MagicMock()
        bm25.search.return_value = [(chunk, 0.9)]
        dense = MagicMock()
        dense.search.return_value = [(chunk, 0.8)]

        layer = CorpusLayer(name="policy", bm25=bm25, dense=dense)
        cfg = RetrievalConfig(
            use_query_decomposition=False,
            use_hyde=False,
            top_k_per_retriever=5,
            top_k_rerank=3,
        )
        reranker = MagicMock()
        reranker.rerank.side_effect = lambda q, candidates, top_k=None: candidates[: (top_k or len(candidates))]

        orch = RetrievalOrchestrator({"policy": layer}, cfg, reranker=reranker)

        async def run():
            return await orch.retrieve("collision damage", top_k=3)

        results = asyncio.run(run())
        assert len(results) >= 1
        assert results[0][0].clause_id == "PART_D.1"

    def test_empty_layers_returns_empty(self) -> None:
        from rag.retrieval.orchestrator import RetrievalConfig, RetrievalOrchestrator

        cfg = RetrievalConfig(use_query_decomposition=False, use_hyde=False)
        orch = RetrievalOrchestrator({}, cfg)

        async def run():
            return await orch.retrieve("anything")

        results = asyncio.run(run())
        assert results == []


# ---------------------------------------------------------------------------
# Query decomposer tests
# ---------------------------------------------------------------------------

class TestQueryDecomposer:
    def test_fallback_on_llm_failure(self) -> None:
        from rag.retrieval.query_decomposer import decompose_query

        with patch("litellm.acompletion", side_effect=Exception("network error")):
            result = asyncio.run(
                decompose_query("what is covered?")
            )
        assert result == ["what is covered?"]

    def test_returns_list_of_strings(self) -> None:
        from rag.retrieval.query_decomposer import decompose_query

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"queries": ["q1", "q2", "q3"]}'
        with patch("litellm.acompletion", return_value=mock_response):
            result = asyncio.run(
                decompose_query("any question", n=3)
            )
        assert result == ["q1", "q2", "q3"]


# ---------------------------------------------------------------------------
# HyDE tests
# ---------------------------------------------------------------------------

class TestHyDE:
    def test_returns_none_for_specific_query(self) -> None:
        from rag.retrieval.hyde import hypothetical_document_embedding

        result = asyncio.run(
            hypothetical_document_embedding("does PART_D.3 cover rental cars?")
        )
        assert result is None  # specific query, gate should block

    def test_fallback_on_llm_failure(self) -> None:
        from rag.retrieval.hyde import hypothetical_document_embedding

        with patch("litellm.acompletion", side_effect=Exception("timeout")):
            result = asyncio.run(
                hypothetical_document_embedding("what does this policy generally cover?")
            )
        assert result is None


# ---------------------------------------------------------------------------
# Citation validator tests
# ---------------------------------------------------------------------------

class TestCitationValidator:
    def _coverage_chunk(self) -> PolicyChunk:
        return _make_chunk(
            "PART_D.1",
            "We will pay for direct and accidental loss to your covered auto. "
            "Coverage applies to collision and comprehensive losses.",
        )

    def _exclusion_chunk(self) -> PolicyChunk:
        return _make_chunk(
            "PART_D.3",
            "We do not cover loss to custom parts or equipment. "
            "This exclusion does not apply if Endorsement VC-004 is attached.",
        )

    def test_layer1_exists_fails(self) -> None:
        result = validate_citation("MISSING_ID", "some text", "covered", [self._coverage_chunk()])
        assert not result.passed
        assert result.failed_at == CitationLayer.EXISTS

    def test_layer1_passes_by_clause_id(self) -> None:
        result = validate_citation(
            "PART_D.1", "We will pay for direct and accidental loss", "covered",
            [self._coverage_chunk()]
        )
        assert result.passed

    def test_layer2_supports_fails_low_overlap(self) -> None:
        result = validate_citation(
            "PART_D.1",
            "completely unrelated words about something entirely different",
            "covered",
            [self._coverage_chunk()],
        )
        assert not result.passed
        assert result.failed_at == CitationLayer.SUPPORTS

    def test_layer3_covers_denial_without_exclusion_language(self) -> None:
        result = validate_citation(
            "PART_D.1",
            "We will pay for direct and accidental loss to your covered auto",
            "denied",
            [self._coverage_chunk()],
        )
        assert not result.passed
        assert result.failed_at == CitationLayer.COVERS

    def test_denial_with_exclusion_language_passes(self) -> None:
        result = validate_citation(
            "PART_D.3",
            "We do not cover loss to custom parts or equipment",
            "denied",
            [self._exclusion_chunk()],
        )
        assert result.passed

    def test_validate_all_empty(self) -> None:
        results = validate_all_citations([], [])
        assert results == []

    def test_pass_rate_all_pass(self) -> None:
        chunk = self._coverage_chunk()
        finding = MagicMock()
        finding.clause_id = "PART_D.1"
        finding.cited_text = "We will pay for direct and accidental loss"
        finding.determination = "covered"
        results = validate_all_citations([finding], [chunk])
        assert citation_pass_rate(results) == 1.0


# ---------------------------------------------------------------------------
# Refusal logic tests
# ---------------------------------------------------------------------------

class TestRefusalLogic:
    def test_no_policy_findings_refuses(self) -> None:
        store = _make_store()
        decision = evaluate_refusal(store)
        assert decision.should_refuse
        assert not decision.escalate_to_human

    def test_high_fraud_escalates(self) -> None:
        store = _make_store(
            policy_findings=[
                PolicyFinding(
                    clause_id="PART_D.1",
                    corpus_layer="policy",
                    determination="covered",
                    cited_text="We will pay",
                    confidence=0.9,
                )
            ],
            fraud_signals=[
                FraudSignal(
                    signal_type="staged_damage",
                    description="suspicious",
                    severity="high",
                    confidence=0.9,
                    source="rule",
                )
            ],
        )
        decision = evaluate_refusal(store)
        assert decision.should_refuse
        assert decision.escalate_to_human

    def test_low_fraud_does_not_refuse(self) -> None:
        store = _make_store(
            policy_findings=[
                PolicyFinding(
                    clause_id="PART_D.1",
                    corpus_layer="policy",
                    determination="covered",
                    cited_text="We will pay",
                    confidence=0.9,
                )
            ],
            fraud_signals=[
                FraudSignal(
                    signal_type="staged_damage",
                    description="minor",
                    severity="low",
                    confidence=0.4,
                    source="rule",
                )
            ],
        )
        decision = evaluate_refusal(store)
        assert not decision.should_refuse

    def test_critical_flags_escalate(self) -> None:
        store = _make_store(
            policy_findings=[
                PolicyFinding(
                    clause_id="PART_D.1",
                    corpus_layer="policy",
                    determination="covered",
                    cited_text="We will pay",
                    confidence=0.9,
                )
            ],
            consistency_flags=[
                ConsistencyFlag(
                    flag_type="date_mismatch",
                    description="conflict 1",
                    severity="critical",
                ),
                ConsistencyFlag(
                    flag_type="damage_narrative_conflict",
                    description="conflict 2",
                    severity="critical",
                ),
            ],
        )
        decision = evaluate_refusal(store)
        assert decision.should_refuse
        assert decision.escalate_to_human

    def test_clean_store_proceeds(self) -> None:
        store = _make_store(
            policy_findings=[
                PolicyFinding(
                    clause_id="PART_D.1",
                    corpus_layer="policy",
                    determination="covered",
                    cited_text="We will pay",
                    confidence=0.9,
                )
            ]
        )
        decision = evaluate_refusal(store)
        assert not decision.should_refuse


# ---------------------------------------------------------------------------
# Endorsement linker tests
# ---------------------------------------------------------------------------

class TestEndorsementLinker:
    def test_build_map(self) -> None:
        chunks = [
            _make_chunk("ENDORSEMENT_VC001.1", "rental reimbursement", "endorsement", modifies="PART_D.2"),
            _make_chunk("ENDORSEMENT_VC001.2", "conditions", "endorsement", modifies="PART_D.2"),
            _make_chunk("PART_D.2", "physical damage", "policy"),
        ]
        endo_map = build_endorsement_map(chunks)
        assert "PART_D.2" in endo_map
        assert len(endo_map["PART_D.2"]) == 2

    def test_no_endorsements(self) -> None:
        chunks = [_make_chunk("PART_A.1", "liability", "policy")]
        assert build_endorsement_map(chunks) == {}

    def test_coverage_check(self) -> None:
        chunks = [
            _make_chunk("ENDORSEMENT_VC001.1", "text", "endorsement", modifies="PART_D.2"),
        ]
        endo_map = build_endorsement_map(chunks)
        # Retrieved master + endorsement
        result = endorsement_coverage(
            ["policy:PART_D.2", "endorsement:ENDORSEMENT_VC001.1"], endo_map
        )
        assert result.get("PART_D.2") is True

    def test_coverage_missing_endorsement(self) -> None:
        chunks = [
            _make_chunk("ENDORSEMENT_VC001.1", "text", "endorsement", modifies="PART_D.2"),
        ]
        endo_map = build_endorsement_map(chunks)
        result = endorsement_coverage(["policy:PART_D.2"], endo_map)
        assert result.get("PART_D.2") is False


# ---------------------------------------------------------------------------
# RAG metrics tests
# ---------------------------------------------------------------------------

class TestRAGMetrics:
    def test_recall_at_k_perfect(self) -> None:
        retrieved = [["C1", "C2", "C3"]]
        relevant = [["C1", "C2"]]
        assert recall_at_k(retrieved, relevant, k=3) == pytest.approx(1.0)

    def test_recall_at_k_partial(self) -> None:
        retrieved = [["C1", "C3"]]
        relevant = [["C1", "C2"]]
        assert recall_at_k(retrieved, relevant, k=2) == pytest.approx(0.5)

    def test_recall_at_k_zero(self) -> None:
        retrieved = [["C3", "C4"]]
        relevant = [["C1", "C2"]]
        assert recall_at_k(retrieved, relevant, k=2) == pytest.approx(0.0)

    def test_mrr_first_hit(self) -> None:
        retrieved = [["C2", "C1", "C3"]]
        relevant = [["C1"]]
        assert mean_reciprocal_rank(retrieved, relevant) == pytest.approx(0.5)

    def test_mrr_no_hit(self) -> None:
        retrieved = [["C3", "C4"]]
        relevant = [["C1"]]
        assert mean_reciprocal_rank(retrieved, relevant) == pytest.approx(0.0)

    def test_endorsement_attachment_rate_full(self) -> None:
        # Both master and endorsement retrieved
        retrieved_sets = [["PART_D.2", "ENDORSEMENT_VC001.1"]]
        master_map = {"PART_D.2": ["ENDORSEMENT_VC001.1"]}
        assert endorsement_attachment_rate(retrieved_sets, master_map) == pytest.approx(1.0)

    def test_endorsement_attachment_rate_missing(self) -> None:
        retrieved_sets = [["PART_D.2"]]  # missing endorsement
        master_map = {"PART_D.2": ["ENDORSEMENT_VC001.1"]}
        assert endorsement_attachment_rate(retrieved_sets, master_map) == pytest.approx(0.0)

    def test_endorsement_attachment_rate_no_masters(self) -> None:
        assert endorsement_attachment_rate([["PART_A.1"]], {}) == pytest.approx(1.0)

    def test_faithfulness_score_high(self) -> None:
        contexts = [["We will pay for direct and accidental loss to your covered auto"]]
        answers = ["We will pay for the covered auto loss"]
        score = faithfulness_score(answers, contexts)
        assert score > 0.3

    def test_faithfulness_score_empty(self) -> None:
        assert faithfulness_score([], []) == pytest.approx(0.0)
