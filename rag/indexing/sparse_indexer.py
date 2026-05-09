"""
BM25 sparse index for policy corpus retrieval.

Uses rank_bm25 (BM25Okapi). One index per corpus layer; stored in-memory
during a session. Serialised to disk via pickle for warm-start loading.
"""
from __future__ import annotations

import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

from rag.ingestion.chunker import PolicyChunk


class BM25Index:
    """Sparse BM25 index over a single corpus layer."""

    def __init__(self) -> None:
        self._chunks: list[PolicyChunk] = []
        self._bm25: BM25Okapi | None = None

    def build(self, chunks: list[PolicyChunk]) -> None:
        self._chunks = chunks
        tokenized = [c.text.lower().split() for c in chunks]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, k: int = 10) -> list[tuple[PolicyChunk, float]]:
        if self._bm25 is None or not self._chunks:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(self._chunks[i], float(s)) for i, s in ranked[:k] if s > 0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        with open(path, "rb") as f:
            return pickle.load(f)

    @property
    def size(self) -> int:
        return len(self._chunks)
