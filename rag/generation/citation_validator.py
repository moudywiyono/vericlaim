"""
Three-layer citation validator for policy-grounded adjudication.

Layer 1 — EXISTS:   the cited clause_id appears in the retrieved chunk set.
Layer 2 — SUPPORTS: the cited text has sufficient word overlap with the chunk body.
Layer 3 — COVERS:   the determination direction (covered/denied) is supported by
                    the type of language in the cited clause.

All three layers must pass for a citation to be considered valid. Failing layers are
reported so the adjudicator can flag weak citations for human review rather than
silently accepting them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rag.ingestion.chunker import PolicyChunk


class CitationLayer(str, Enum):
    EXISTS = "exists"
    SUPPORTS = "supports"
    COVERS = "covers"


@dataclass
class CitationValidationResult:
    clause_id: str
    passed: bool
    failed_at: CitationLayer | None  # first layer that failed; None if passed
    message: str


_DENIAL_KEYWORDS = frozenset({
    "exclusion",
    "does not cover",
    "not covered",
    "shall not",
    "excluded",
    "we do not",
    "we will not",
    "does not apply",
    "not apply",
})
_COVERAGE_KEYWORDS = frozenset({
    "we will pay",
    "coverage",
    "covered",
    "pay for",
    "reimburse",
    "we will provide",
    "we will cover",
})
_SUPPORTS_THRESHOLD = 0.5  # minimum word overlap fraction for layer 2


def validate_citation(
    clause_id: str,
    cited_text: str,
    determination: str,
    retrieved_chunks: list[PolicyChunk],
) -> CitationValidationResult:
    """
    Validate a single citation against the retrieved chunk set.

    clause_id: the clause ID cited by the policy reasoner (e.g. "PART_D.3")
    cited_text: verbatim excerpt the reasoner pulled from the clause
    determination: the coverage determination ("covered", "denied", etc.)
    retrieved_chunks: chunks returned by the retrieval pipeline for this claim
    """
    # Layer 1: EXISTS
    chunk: PolicyChunk | None = None
    for c in retrieved_chunks:
        if c.chunk_id == clause_id or c.clause_id == clause_id:
            chunk = c
            break
        # Also match bare clause_id embedded in chunk_id (e.g. "policy:PART_D.3")
        if clause_id in c.chunk_id:
            chunk = c
            break

    if chunk is None:
        return CitationValidationResult(
            clause_id=clause_id,
            passed=False,
            failed_at=CitationLayer.EXISTS,
            message=f"Clause {clause_id!r} not found in retrieved chunk set",
        )

    # Layer 2: SUPPORTS
    if cited_text and cited_text.strip():
        cited_words = set(cited_text.lower().split())
        chunk_words = set(chunk.text.lower().split())
        overlap = len(cited_words & chunk_words) / max(len(cited_words), 1)
        if overlap < _SUPPORTS_THRESHOLD:
            return CitationValidationResult(
                clause_id=clause_id,
                passed=False,
                failed_at=CitationLayer.SUPPORTS,
                message=(
                    f"Cited text has {overlap:.0%} word overlap with chunk body "
                    f"(threshold {_SUPPORTS_THRESHOLD:.0%})"
                ),
            )

    # Layer 3: COVERS
    det_lower = determination.lower()
    chunk_lower = chunk.text.lower()

    if "denied" in det_lower or "deny" in det_lower or "exclusion" in det_lower:
        if not any(kw in chunk_lower for kw in _DENIAL_KEYWORDS):
            return CitationValidationResult(
                clause_id=clause_id,
                passed=False,
                failed_at=CitationLayer.COVERS,
                message=(
                    "Denial determination cited, but no exclusion language found in clause"
                ),
            )
    elif "covered" in det_lower or "approve" in det_lower or "partial" in det_lower:
        if not any(kw in chunk_lower for kw in _COVERAGE_KEYWORDS):
            return CitationValidationResult(
                clause_id=clause_id,
                passed=False,
                failed_at=CitationLayer.COVERS,
                message=(
                    "Coverage determination cited, but no coverage language found in clause"
                ),
            )

    return CitationValidationResult(
        clause_id=clause_id,
        passed=True,
        failed_at=None,
        message="OK",
    )


def validate_all_citations(
    policy_findings: list,  # list[PolicyFinding] — avoid circular import
    retrieved_chunks: list[PolicyChunk],
) -> list[CitationValidationResult]:
    """Validate every citation in a list of PolicyFinding objects."""
    return [
        validate_citation(
            f.clause_id,
            f.cited_text,
            f.determination,
            retrieved_chunks,
        )
        for f in policy_findings
    ]


def citation_pass_rate(results: list[CitationValidationResult]) -> float:
    """Fraction of citations that passed all three layers."""
    if not results:
        return 1.0
    return sum(r.passed for r in results) / len(results)
