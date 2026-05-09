"""
Retrieval evaluation harness for the RAG pipeline.

Thin wrapper that runs the retrieval orchestrator against a dataset of
(query, gold_clause_ids) pairs and computes recall@k, MRR, and
endorsement attachment rate.

Dataset format (JSON lines):
  {"query": "...", "relevant_clause_ids": ["PART_D.3", "ENDORSEMENT_VC001.1"]}
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from evals.metrics.rag_metrics import (
    endorsement_attachment_rate,
    mean_reciprocal_rank,
    recall_at_k,
)
from rag.ingestion.endorsement_linker import build_endorsement_map
from rag.ingestion.chunker import load_corpus
from rag.retrieval.orchestrator import RetrievalConfig, RetrievalOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class RetrievalEvalResult:
    recall_at_5: float
    recall_at_10: float
    mrr: float
    endorsement_attachment_rate: float
    num_queries: int


async def run_retrieval_eval(
    orchestrator: RetrievalOrchestrator,
    dataset_path: Path,
    top_k: int = 10,
    corpus_dir: Path | None = None,
) -> RetrievalEvalResult:
    """
    Evaluate retrieval quality against a labelled dataset.

    orchestrator: pre-built RetrievalOrchestrator (no model downloads in eval)
    dataset_path: JSONL file with {"query": ..., "relevant_clause_ids": [...]}
    corpus_dir: used only to build the endorsement map; optional
    """
    records = [
        json.loads(line)
        for line in dataset_path.read_text().splitlines()
        if line.strip()
    ]

    queries = [r["query"] for r in records]
    gold_ids = [r["relevant_clause_ids"] for r in records]

    # Run all queries
    all_retrieved: list[list[str]] = []
    for query in queries:
        results = await orchestrator.retrieve(query, top_k=top_k)
        all_retrieved.append([chunk.chunk_id for chunk, _ in results])

    # Build endorsement map if corpus_dir provided
    endo_map: dict[str, list[str]] = {}
    if corpus_dir:
        all_chunks = []
        for chunks in load_corpus(corpus_dir).values():
            all_chunks.extend(chunks)
        endo_map = build_endorsement_map(all_chunks)

    return RetrievalEvalResult(
        recall_at_5=recall_at_k(all_retrieved, gold_ids, k=5),
        recall_at_10=recall_at_k(all_retrieved, gold_ids, k=10),
        mrr=mean_reciprocal_rank(all_retrieved, gold_ids),
        endorsement_attachment_rate=endorsement_attachment_rate(
            all_retrieved, endo_map
        ),
        num_queries=len(queries),
    )
