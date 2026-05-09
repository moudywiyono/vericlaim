"""
Citation quality evaluation for policy-grounded adjudication.

Evaluates a list of PolicyFindings against the retrieved chunks that were
available to the policy reasoner when producing them. Computes per-layer
pass rates and surfaces specific citation failures for error analysis.
"""
from __future__ import annotations

from dataclasses import dataclass

from rag.generation.citation_validator import (
    CitationLayer,
    CitationValidationResult,
    citation_pass_rate,
    validate_all_citations,
)
from rag.ingestion.chunker import PolicyChunk


@dataclass
class CitationEvalResult:
    overall_pass_rate: float
    exists_pass_rate: float
    supports_pass_rate: float
    covers_pass_rate: float
    num_citations: int
    failures: list[CitationValidationResult]


def evaluate_citations(
    policy_findings: list,  # list[PolicyFinding]
    retrieved_chunks: list[PolicyChunk],
) -> CitationEvalResult:
    """
    Evaluate citation quality for a set of PolicyFindings.

    Returns per-layer pass rates and the list of failed citations for debugging.
    """
    results = validate_all_citations(policy_findings, retrieved_chunks)
    if not results:
        return CitationEvalResult(
            overall_pass_rate=1.0,
            exists_pass_rate=1.0,
            supports_pass_rate=1.0,
            covers_pass_rate=1.0,
            num_citations=0,
            failures=[],
        )

    failures = [r for r in results if not r.passed]

    def layer_pass_rate(layer: CitationLayer) -> float:
        reached = [r for r in results if r.failed_at is None or r.failed_at != layer]
        # Count as passing at this layer if: passed overall, or failed at a later layer
        at_layer = [
            r
            for r in results
            if r.failed_at is None
            or list(CitationLayer).index(r.failed_at) > list(CitationLayer).index(layer)
            or r.passed
        ]
        passed_at_layer = [
            r
            for r in results
            if r.passed or (
                r.failed_at is not None
                and list(CitationLayer).index(r.failed_at)
                > list(CitationLayer).index(layer)
            )
        ]
        return len(passed_at_layer) / max(len(results), 1)

    return CitationEvalResult(
        overall_pass_rate=citation_pass_rate(results),
        exists_pass_rate=layer_pass_rate(CitationLayer.EXISTS),
        supports_pass_rate=layer_pass_rate(CitationLayer.SUPPORTS),
        covers_pass_rate=layer_pass_rate(CitationLayer.COVERS),
        num_citations=len(results),
        failures=failures,
    )
