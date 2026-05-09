"""
Definition lookup and injection utilities.

Exposes the _DEFINITION_TERMS table from the chunker as a public API so other
modules can look up definitions without importing private symbols.
"""
from __future__ import annotations

from rag.ingestion.chunker import _DEFINITION_TERMS, PolicyChunk


def get_definition(term: str) -> str | None:
    """Return the canonical definition for a term, or None if not in the glossary."""
    return _DEFINITION_TERMS.get(term.lower())


def list_defined_terms() -> list[str]:
    """Return all terms in the policy glossary."""
    return list(_DEFINITION_TERMS.keys())


def chunks_defining_term(term: str, chunks: list[PolicyChunk]) -> list[PolicyChunk]:
    """Return chunks that have the given definition term appended to their body."""
    return [c for c in chunks if term in c.definitions_appended]


def inject_missing_definitions(
    query: str,
    retrieved_chunks: list[PolicyChunk],
) -> str:
    """
    Append definitions for any glossary terms in the query that are not already
    covered by the retrieved chunks.

    This handles the edge case where a query contains defined terms but the
    definition chunks were not retrieved (e.g. because they were outranked by
    more specific clauses).
    """
    covered_terms: set[str] = set()
    for chunk in retrieved_chunks:
        covered_terms.update(chunk.definitions_appended)

    query_lower = query.lower()
    missing_defs: list[str] = []
    for term, definition in _DEFINITION_TERMS.items():
        if term in query_lower and term not in covered_terms:
            missing_defs.append(f"- {term.title()}: {definition}")

    if not missing_defs:
        return query
    return query + "\n\n[Relevant definitions]\n" + "\n".join(missing_defs)
