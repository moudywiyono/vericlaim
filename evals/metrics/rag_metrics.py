"""
RAG / Policy Reasoner evaluation metrics.
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
    if not retrieved_ids:
        return 0.0
    total = 0.0
    for retrieved, relevant in zip(retrieved_ids, relevant_ids):
        relevant_set = set(relevant)
        if not relevant_set:
            total += 1.0
            continue
        top_k = set(retrieved[:k])
        total += len(top_k & relevant_set) / len(relevant_set)
    return total / len(retrieved_ids)


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
    if not retrieved_ids:
        return 0.0
    total = 0.0
    for retrieved, relevant in zip(retrieved_ids, relevant_ids):
        relevant_set = set(relevant)
        for rank, cid in enumerate(retrieved, start=1):
            if cid in relevant_set:
                total += 1.0 / rank
                break
    return total / len(retrieved_ids)


def faithfulness_score(
    generated_answers: list[str],
    retrieved_contexts: list[list[str]],
) -> float:
    """
    Faithfulness: fraction of claims in each generated answer that are
    attributable to the retrieved context (word-overlap approximation).

    Args:
        generated_answers: list of generated adjudication texts
        retrieved_contexts: per-answer list of retrieved clause texts
    Returns:
        mean faithfulness score in [0, 1]
    """
    if not generated_answers:
        return 0.0
    total = 0.0
    for answer, contexts in zip(generated_answers, retrieved_contexts):
        if not contexts:
            continue
        context_words = set(" ".join(contexts).lower().split())
        # Split on period to approximate sentence boundaries
        sentences = [s.strip() for s in answer.split(".") if s.strip()]
        if not sentences:
            continue
        faithful_count = sum(
            len(set(s.lower().split()) & context_words) / max(len(s.split()), 1) >= 0.4
            for s in sentences
        )
        total += faithful_count / len(sentences)
    return total / len(generated_answers)


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
        attachment rate in [0, 1]; 1.0 if no master clauses have endorsements
    """
    if not master_to_endorsements:
        return 1.0
    total_opportunities = 0
    attached = 0
    for retrieved in retrieved_id_sets:
        retrieved_set = set(retrieved)
        for master_id, endorsement_ids in master_to_endorsements.items():
            if master_id in retrieved_set and endorsement_ids:
                total_opportunities += 1
                if all(eid in retrieved_set for eid in endorsement_ids):
                    attached += 1
    return attached / max(total_opportunities, 1)
