"""
Hypothetical Document Embedding (HyDE) for abstract policy queries.

For abstract questions ("what does the policy generally cover?"), generates a
hypothetical policy clause that would answer the question, then uses that clause
as an additional dense retrieval query. This bridges the vocabulary gap between
natural-language questions and formal policy language.

Gate: HyDE is only applied to queries that look abstract (contain keywords like
"generally", "explain", "what is"). Specific queries ("does PART_D cover rental?")
skip HyDE to avoid introducing noise.
"""
from __future__ import annotations

import logging
import os

import litellm

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")

_HYDE_PROMPT = """\
You are an insurance policy expert. Write a brief (2-3 sentence) hypothetical policy \
clause that would directly answer the following question. Write in the formal, precise \
language of an actual insurance policy document.

Question: {question}

Hypothetical policy clause:"""

_ABSTRACT_KEYWORDS = frozenset({
    "generally",
    "typically",
    "usually",
    "in general",
    "overall",
    "what does",
    "how does",
    "explain",
    "describe",
    "what is",
    "tell me about",
    "overview",
    "summary",
})


def _is_abstract(query: str) -> bool:
    lower = query.lower()
    return any(kw in lower for kw in _ABSTRACT_KEYWORDS)


async def hypothetical_document_embedding(question: str) -> str | None:
    """
    Generate a hypothetical policy clause for abstract queries.

    Returns None for specific/concrete queries or if generation fails.
    """
    if not _is_abstract(question):
        return None
    try:
        response = await litellm.acompletion(
            model=_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": _HYDE_PROMPT.format(question=question),
                }
            ],
            temperature=0.3,
        )
        text = response.choices[0].message.content or ""
        return text.strip() or None
    except Exception as e:
        logger.warning("HyDE generation failed (%s); skipping", e)
        return None
