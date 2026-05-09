"""
Dense vector index for policy corpus retrieval.

Uses sentence-transformers for embeddings. Model is lazy-loaded on first use.
Configurable via VERICLAIM_DENSE_MODEL env var; defaults to bge-large-en-v1.5
(production) but any sentence-transformers model works.

For tests, patch DenseIndex.build / DenseIndex.search directly — no model
download required.
"""
from __future__ import annotations

import os
import pickle
from pathlib import Path

import numpy as np

from rag.ingestion.chunker import PolicyChunk

_DENSE_MODEL = os.getenv("VERICLAIM_DENSE_MODEL", "BAAI/bge-large-en-v1.5")


class DenseIndex:
    """Dense cosine-similarity index over a single corpus layer."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or _DENSE_MODEL
        self._chunks: list[PolicyChunk] = []
        self._embeddings: np.ndarray | None = None
        self._model: object | None = None  # cached after first load

    def _get_model(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def build(self, chunks: list[PolicyChunk]) -> None:
        model = self._get_model()
        self._chunks = chunks
        self._embeddings = model.encode(  # type: ignore[union-attr]
            [c.text for c in chunks],
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def search(self, query: str, k: int = 10) -> list[tuple[PolicyChunk, float]]:
        if self._embeddings is None or not self._chunks:
            return []
        model = self._get_model()
        q_emb = model.encode([query], normalize_embeddings=True)  # type: ignore[union-attr]
        scores = (self._embeddings @ q_emb.T).squeeze()
        if scores.ndim == 0:
            scores = scores.reshape(1)
        ranked = sorted(enumerate(scores.tolist()), key=lambda x: x[1], reverse=True)
        return [(self._chunks[i], float(s)) for i, s in ranked[:k]]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: Path) -> "DenseIndex":
        with open(path, "rb") as f:
            return pickle.load(f)

    @property
    def size(self) -> int:
        return len(self._chunks)
