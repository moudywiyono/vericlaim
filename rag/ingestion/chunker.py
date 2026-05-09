"""
Section-aware policy document chunker.

Parses VeriClaim Mutual policy text into PolicyChunk objects. Each chunk carries
its full section path, clause_id, parent summary, and cross-references — preserving
the semantic structure that general-purpose RAG chunkers destroy.

Parsing contract:
  - CLAUSE_ID: lines mark chunk boundaries
  - SECTION: / SUBSECTION: / ENDORSEMENT: / MODIFIES: lines provide metadata
  - Text following the metadata block is the chunk body
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class PolicyChunk(BaseModel):
    chunk_id: str
    corpus: Literal["policy", "endorsement", "regulation", "guideline"]
    clause_id: str
    path: list[str]               # breadcrumb from doc root to this clause
    text: str                     # chunk body text
    parent_summary: str           # one-line summary of the parent section
    cross_refs: list[str]         # clause_ids this chunk explicitly references
    definitions_appended: list[str]  # definition terms duplicated into this chunk
    endorsement_id: str | None = None  # set for endorsement chunks
    modifies: str | None = None        # clause_id this endorsement modifies


# Key terms to duplicate into referencing chunks (improves retrieval accuracy)
_DEFINITION_TERMS = {
    "collision": (
        "Collision means the upset of your covered auto or a non-owned auto "
        "or their impact with another vehicle or object."
    ),
    "total loss": (
        "Total loss means damage where repair costs plus salvage value equal "
        "or exceed the actual cash value of the covered auto; we declare a "
        "total loss when estimated repair costs exceed 75% of pre-loss market value."
    ),
    "deductible": (
        "Deductible means the amount you must pay before we cover a loss."
    ),
    "covered auto": (
        "Covered auto means any vehicle shown in the Declarations for which "
        "a premium charge is indicated."
    ),
    "loss": (
        "Loss means direct and accidental loss or damage to a covered auto "
        "or non-owned auto, including their equipment."
    ),
    "market value": (
        "Market value means the amount a willing buyer would pay a willing "
        "seller in an arm's length transaction at the time of the loss."
    ),
}

# Cross-reference patterns: "PART X", "Section X", "Endorsement VC-NNN", "PART_X.N"
_XREF_PATTERN = re.compile(
    r"\b(PART\s+[A-F](?:\.[0-9]+(?:\.[a-z])?)?|"
    r"Endorsement\s+VC-\d{3}|"
    r"ENDORSEMENT_VC\d{3}(?:\.\d+)?|"
    r"PART_[A-F]\.[0-9]+(?:\.[a-z])?)\b",
    re.IGNORECASE,
)


def _extract_cross_refs(text: str, own_clause_id: str) -> list[str]:
    """Extract clause_id references from text, excluding self-references."""
    found = set()
    for m in _XREF_PATTERN.finditer(text):
        ref = m.group(0).strip().upper().replace(" ", "_").replace("-", "_")
        if ref != own_clause_id.upper():
            found.add(ref)
    return sorted(found)


def _detect_definitions(text: str) -> list[str]:
    """Return definition terms whose keywords appear in this chunk's text."""
    lower = text.lower()
    return [term for term in _DEFINITION_TERMS if term in lower]


def _build_parent_summary(path: list[str]) -> str:
    if not path:
        return ""
    return " > ".join(path[-2:]) if len(path) >= 2 else path[0]


def parse_corpus_file(
    path: Path,
    corpus: Literal["policy", "endorsement", "regulation", "guideline"],
) -> list[PolicyChunk]:
    """
    Parse a corpus text file into PolicyChunk objects.

    Each chunk is delimited by a CLAUSE_ID: line. Metadata lines immediately
    following CLAUSE_ID (SECTION:, SUBSECTION:, ENDORSEMENT:, MODIFIES:) are
    consumed as structured metadata; remaining lines form the chunk body.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    chunks: list[PolicyChunk] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line.startswith("CLAUSE_ID:"):
            i += 1
            continue

        clause_id = line[len("CLAUSE_ID:"):].strip()
        i += 1

        # Consume metadata lines
        section: str = ""
        subsection: str = ""
        endorsement_id: str | None = None
        modifies: str | None = None

        while i < len(lines):
            meta = lines[i].strip()
            if meta.startswith("SECTION:"):
                section = meta[len("SECTION:"):].strip()
                i += 1
            elif meta.startswith("SUBSECTION:"):
                subsection = meta[len("SUBSECTION:"):].strip()
                i += 1
            elif meta.startswith("ENDORSEMENT:"):
                endorsement_id = meta[len("ENDORSEMENT:"):].strip()
                i += 1
            elif meta.startswith("MODIFIES:"):
                modifies = meta[len("MODIFIES:"):].strip()
                i += 1
            else:
                break

        # Collect body lines until next CLAUSE_ID or separator
        body_lines: list[str] = []
        while i < len(lines):
            peek = lines[i].strip()
            if peek.startswith("CLAUSE_ID:"):
                break
            if peek.startswith("=" * 10):
                i += 1
                continue
            body_lines.append(lines[i])
            i += 1

        body = "\n".join(body_lines).strip()
        if not body:
            continue

        # Build path breadcrumb
        path_parts: list[str] = []
        if section:
            path_parts.append(section)
        if subsection:
            path_parts.append(subsection)

        cross_refs = _extract_cross_refs(body, clause_id)
        definitions = _detect_definitions(body)

        # Append definition text for key terms found in this chunk
        full_text = body
        if definitions:
            appended = "\n\n[Definitions for terms used above]\n"
            appended += "\n".join(
                f"- {term.title()}: {_DEFINITION_TERMS[term]}"
                for term in definitions
            )
            full_text = body + appended

        chunk = PolicyChunk(
            chunk_id=f"{corpus}:{clause_id}",
            corpus=corpus,
            clause_id=clause_id,
            path=path_parts,
            text=full_text,
            parent_summary=_build_parent_summary(path_parts),
            cross_refs=cross_refs,
            definitions_appended=definitions,
            endorsement_id=endorsement_id,
            modifies=modifies,
        )
        chunks.append(chunk)

    return chunks


def load_corpus(
    corpus_dir: Path,
) -> dict[Literal["policy", "endorsement", "regulation", "guideline"], list[PolicyChunk]]:
    """
    Load and chunk all corpus files from a directory.

    Expected filenames: policy.txt, endorsements.txt, regulations.txt, guidelines.txt.
    Missing files are silently skipped (not all corpora are required).
    """
    mapping: dict[str, Literal["policy", "endorsement", "regulation", "guideline"]] = {
        "policy.txt": "policy",
        "endorsements.txt": "endorsement",
        "regulations.txt": "regulation",
        "guidelines.txt": "guideline",
    }
    result: dict[str, list[PolicyChunk]] = {}
    for filename, corpus_type in mapping.items():
        p = corpus_dir / filename
        if p.exists():
            result[corpus_type] = parse_corpus_file(p, corpus_type)
    return result  # type: ignore[return-value]
