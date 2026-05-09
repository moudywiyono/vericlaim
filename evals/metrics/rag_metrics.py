"""
RAG / Policy Reasoner evaluation metrics.
Stubs with correct signatures — implementations in Phase 2 (RAG build).
"""
from __future__ import annotations


def recall_at_k(
    retrieved_ids: list[list[str]],
    relevant_ids: list[list[str]],
    k: int,
) -> float:
    """
    Mean Recall@k: fraction of relevant clause IDs that appear in the top-k results.

    Args:
        retrieved_ids: per-query list of retrieved clause IDs (ordered by rank)
        relevant_ids: per-query list of gold relevant clause IDs
        k: cutoff
    Returns:
        mean Recall@k across all queries
    """
    raise NotImplementedError


def mean_reciprocal_rank(
    retrieved_ids: list[list[str]],
    relevant_ids: list[list[str]],
) -> float:
    """
    MRR: mean of reciprocal rank of the first relevant result per query.

    Args:
        retrieved_ids: per-query ranked list of retrieved clause IDs
        relevant_ids: per-query list of gold relevant clause IDs
    Returns:
        MRR in [0, 1]
    """
    raise NotImplementedError


def faithfulness_score(
    generated_answers: list[str],
    retrieved_contexts: list[list[str]],
) -> float:
    """
    Faithfulness: fraction of claims in each generated answer that are
    attributable to the retrieved context (RAGAS-style).

    Args:
        generated_answers: list of generated adjudication texts
        retrieved_contexts: per-answer list of retrieved clause texts
    Returns:
        mean faithfulness score in [0, 1]
    """
    raise NotImplementedError


def endorsement_attachment_rate(
    retrieved_id_sets: list[list[str]],
    master_to_endorsements: dict[str, list[str]],
) -> float:
    """
    Fraction of retrievals that correctly include all modifying endorsements
    when the retrieved master clause has endorsements.

    This is a domain-specific metric that catches a class of bugs generic
    retrieval metrics miss: retrieving the master clause without its modifiers.

    Args:
        retrieved_id_sets: per-query list of retrieved clause IDs
        master_to_endorsements: mapping of master clause ID → [endorsement IDs]
    Returns:
        attachment rate in [0, 1]
    """
    raise NotImplementedError
