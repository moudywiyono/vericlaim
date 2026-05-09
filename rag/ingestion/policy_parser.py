"""
High-level corpus loading API.

Thin wrapper around chunker.load_corpus that provides caching and validation.
Use this in the PolicyReasonerNode and RetrievalOrchestrator rather than calling
chunker.load_corpus directly — it logs chunk counts and warns on empty corpora.
"""
from __future__ import annotations

import logging
from pathlib import Path

from rag.ingestion.chunker import PolicyChunk, load_corpus

logger = logging.getLogger(__name__)

_EXPECTED_CORPORA = {"policy", "endorsement"}  # regulation/guideline are optional


def load_and_validate_corpus(
    corpus_dir: Path,
) -> dict[str, list[PolicyChunk]]:
    """
    Load all corpus files from corpus_dir and log chunk counts.

    Warns if required corpora (policy, endorsement) are missing or empty.
    Missing optional corpora (regulation, guideline) are silently skipped.
    """
    result = load_corpus(corpus_dir)

    for corpus_name, chunks in result.items():
        logger.info("Loaded corpus %r: %d chunks", corpus_name, len(chunks))
        if not chunks:
            logger.warning("Corpus %r loaded but contains zero chunks", corpus_name)

    for required in _EXPECTED_CORPORA:
        if required not in result or not result[required]:
            logger.warning(
                "Required corpus %r is missing or empty in %s", required, corpus_dir
            )

    return result
