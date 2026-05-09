"""
Reciprocal Rank Fusion (RRF) for hybrid BM25 + dense retrieval.

RRF is parameter-robust: the k=60 constant dampens the impact of absolute
scores and lets rank position dominate, which works well when combining
retrieval systems with incompatible score distributions.
"""
from __future__ import annotations

from rag.ingestion.chunker import PolicyChunk


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[PolicyChunk, float]]],
    k: int = 60,
) -> list[tuple[PolicyChunk, float]]:
    """
    Fuse multiple ranked result lists using RRF.

    Args:
        ranked_lists: Each inner list is a ranked [(chunk, score), ...] from
                      one retrieval system (BM25, dense, etc.).
        k: RRF constant (default 60, per Cormack et al. 2009).
    Returns:
        Unified ranked list of (chunk, rrf_score), highest score first.
    """
    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, PolicyChunk] = {}

    for ranked in ranked_lists:
        for rank, (chunk, _) in enumerate(ranked):
            rrf_scores[chunk.chunk_id] = (
                rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            )
            chunk_map[chunk.chunk_id] = chunk

    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
    return [(chunk_map[cid], rrf_scores[cid]) for cid in sorted_ids]
