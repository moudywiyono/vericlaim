"""
Retrieval orchestrator — ties BM25, dense, RRF, reranker, query decomposition,
and HyDE into a single async `retrieve(query)` call.

Pipeline per query:
  1. Decompose query into N sub-queries (LLM, falls back to original on failure)
  2. For abstract queries, generate a HyDE document (LLM, optional)
  3. For each sub-query × corpus layer: BM25 search + dense search
  4. Add HyDE-based dense search results (if generated)
  5. Fuse all ranked lists via Reciprocal Rank Fusion
  6. Rerank fused results with cross-encoder (optional, degrades gracefully)

Corpus layers are indexed on first `from_corpus_dir()` call; subsequent calls
reuse the in-memory indexes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from rag.indexing.dense_indexer import DenseIndex
from rag.indexing.sparse_indexer import BM25Index
from rag.ingestion.chunker import PolicyChunk
from rag.retrieval.hybrid import reciprocal_rank_fusion
from rag.retrieval.hyde import hypothetical_document_embedding
from rag.retrieval.query_decomposer import decompose_query
from rag.retrieval.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


@dataclass
class CorpusLayer:
    name: str
    bm25: BM25Index
    dense: DenseIndex


@dataclass
class RetrievalConfig:
    top_k_per_retriever: int = 10
    top_k_rerank: int = 5
    use_query_decomposition: bool = True
    use_hyde: bool = True
    corpus_layers: list[str] = field(
        default_factory=lambda: ["policy", "endorsement", "regulation", "guideline"]
    )


class RetrievalOrchestrator:
    """
    End-to-end retrieval pipeline for a multi-corpus policy index.

    Construct via `from_corpus_dir()` for production, or inject layers directly
    in tests (no model downloads required when layers are mocked).
    """

    def __init__(
        self,
        layers: dict[str, CorpusLayer],
        config: RetrievalConfig | None = None,
        reranker: CrossEncoderReranker | None = None,
    ) -> None:
        self._layers = layers
        self._config = config or RetrievalConfig()
        self._reranker = reranker or CrossEncoderReranker()

    @classmethod
    def from_corpus_dir(
        cls,
        corpus_dir: Path,
        config: RetrievalConfig | None = None,
    ) -> "RetrievalOrchestrator":
        """Build indexes from corpus text files. Downloads embedding model on first call."""
        from rag.ingestion.chunker import load_corpus

        cfg = config or RetrievalConfig()
        chunks_by_corpus = load_corpus(corpus_dir)

        layers: dict[str, CorpusLayer] = {}
        for corpus_name, chunks in chunks_by_corpus.items():
            if corpus_name not in cfg.corpus_layers:
                continue
            bm25 = BM25Index()
            bm25.build(chunks)
            dense = DenseIndex()
            dense.build(chunks)
            layers[corpus_name] = CorpusLayer(name=corpus_name, bm25=bm25, dense=dense)
            logger.info(
                "Indexed corpus %r: %d chunks (BM25 + dense)", corpus_name, len(chunks)
            )

        return cls(layers, cfg)

    async def retrieve(
        self, query: str, top_k: int | None = None
    ) -> list[tuple[PolicyChunk, float]]:
        """
        Retrieve and rerank the top-k most relevant policy chunks for a query.

        Returns an empty list if no corpus layers are loaded.
        """
        cfg = self._config
        k = top_k if top_k is not None else cfg.top_k_rerank

        if not self._layers:
            return []

        # Step 1: query decomposition
        queries = (
            await decompose_query(query)
            if cfg.use_query_decomposition
            else [query]
        )

        # Step 2: HyDE document (gated on abstract queries)
        hyde_doc: str | None = (
            await hypothetical_document_embedding(query)
            if cfg.use_hyde
            else None
        )

        # Step 3–4: search all layers with all queries + HyDE
        all_ranked: list[list[tuple[PolicyChunk, float]]] = []
        for q in queries:
            for layer_name, layer in self._layers.items():
                bm25_results = layer.bm25.search(q, k=cfg.top_k_per_retriever)
                dense_results = layer.dense.search(q, k=cfg.top_k_per_retriever)
                if bm25_results:
                    all_ranked.append(bm25_results)
                if dense_results:
                    all_ranked.append(dense_results)

            if hyde_doc:
                for layer in self._layers.values():
                    hyde_results = layer.dense.search(
                        hyde_doc, k=max(cfg.top_k_per_retriever // 2, 1)
                    )
                    if hyde_results:
                        all_ranked.append(hyde_results)

        if not all_ranked:
            return []

        # Step 5: RRF fusion
        fused = reciprocal_rank_fusion(all_ranked)

        # Step 6: cross-encoder reranking (degrades to RRF order if unavailable)
        return self._reranker.rerank(query, fused, top_k=k)
