"""
Endorsement-to-master-clause linker.

Builds the mapping {master_clause_id: [endorsement_chunk_ids]} from a loaded corpus.
Used by:
  - RetrievalOrchestrator: to co-retrieve endorsements alongside master clauses
  - eval/retrieval_eval.py: to compute endorsement_attachment_rate
"""
from __future__ import annotations

from rag.ingestion.chunker import PolicyChunk


def build_endorsement_map(
    chunks: list[PolicyChunk],
) -> dict[str, list[str]]:
    """
    Build {master_clause_id: [endorsement_chunk_ids]} from a flat chunk list.

    Only endorsement chunks with a non-None `modifies` field are included.
    The key is the bare clause_id of the master clause; the values are the
    full chunk_ids of the modifying endorsements.
    """
    mapping: dict[str, list[str]] = {}
    for chunk in chunks:
        if chunk.modifies:
            # modifies is a bare clause_id (e.g. "PART_D.2")
            mapping.setdefault(chunk.modifies, []).append(chunk.chunk_id)
    return mapping


def get_endorsements_for_clause(
    clause_id: str,
    endorsement_map: dict[str, list[str]],
) -> list[str]:
    """Return all endorsement chunk_ids that modify the given clause_id."""
    return endorsement_map.get(clause_id, [])


def endorsement_coverage(
    retrieved_chunk_ids: list[str],
    endorsement_map: dict[str, list[str]],
) -> dict[str, bool]:
    """
    For each master clause in the retrieved set that has endorsements, check
    whether all modifying endorsements were also retrieved.

    Returns {master_clause_id: all_endorsements_present}.

    Accepts both bare clause_ids ("PART_D.2") and prefixed chunk_ids
    ("policy:PART_D.2") in retrieved_chunk_ids.
    """
    result: dict[str, bool] = {}
    retrieved_set = set(retrieved_chunk_ids)
    # Also accept bare clause_ids (strip corpus: prefix for matching)
    bare_ids = {cid.split(":", 1)[-1] for cid in retrieved_set} | retrieved_set
    for master_id, endorsement_ids in endorsement_map.items():
        if master_id in bare_ids:
            result[master_id] = all(
                eid in bare_ids or eid.split(":", 1)[-1] in bare_ids
                for eid in endorsement_ids
            )
    return result
