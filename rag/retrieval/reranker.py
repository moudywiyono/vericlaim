"""
Cross-encoder reranker for policy clause retrieval.

Uses BAAI/bge-reranker-v2-m3 by default, configurable via VERICLAIM_RERANKER_MODEL.
Degrades gracefully to pass-through if the model is unavailable — the pipeline
continues without reranking rather than failing hard.

For tests, patch CrossEncoderReranker.rerank directly; no model download needed.
"""
from __future__ import annotations

import logging
import os

from rag.ingestion.chunker import PolicyChunk

logger = logging.getLogger(__name__)

_RERANKER_MODEL = os.getenv("VERICLAIM_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")


class CrossEncoderReranker:
    """Cross-encoder reranker over (query, chunk) pairs."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or _RERANKER_MODEL
        self._model = None
        self._available: bool | None = None  # None = untested

    def _load(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
            self._available = True
            logger.debug("CrossEncoder %s loaded", self._model_name)
        except Exception as e:
            logger.warning(
                "CrossEncoder unavailable (%s); reranker will pass-through", e
            )
            self._available = False
        return self._available  # type: ignore[return-value]

    def rerank(
        self,
        query: str,
        candidates: list[tuple[PolicyChunk, float]],
        top_k: int | None = None,
    ) -> list[tuple[PolicyChunk, float]]:
        """
        Rerank candidates using the cross-encoder.

        Falls back to original RRF order if model is unavailable.
        top_k=None returns all candidates.
        """
        k = top_k if top_k is not None else len(candidates)
        if not candidates:
            return []
        if not self._load():
            return candidates[:k]

        pairs = [[query, chunk.text] for chunk, _ in candidates]
        scores = self._model.predict(pairs)  # type: ignore[union-attr]
        ranked = sorted(
            zip(candidates, scores.tolist() if hasattr(scores, "tolist") else scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(chunk, float(s)) for (chunk, _), s in ranked[:k]]
