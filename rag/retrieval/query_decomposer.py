"""
LLM-based query decomposition for multi-facet policy retrieval.

Given a claims question, generates N sub-queries that target different facets
(coverage grants, exclusions, conditions, definitions). Falls back to the
original query if the LLM call fails — retrieval still runs.
"""
from __future__ import annotations

import json
import logging
import os

import litellm

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_DEFAULT_N = 3

_DECOMPOSE_PROMPT = """\
You are a policy retrieval assistant. Given a claims question, generate {n} distinct \
search queries that together cover the most important aspects of the question. Each \
query should target a different facet: coverage grants, exclusions, conditions, \
or key definitions.

Question: {question}

Respond with valid JSON only, no markdown fences:
{{"queries": ["query 1", "query 2", "query 3"]}}"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


async def decompose_query(question: str, n: int = _DEFAULT_N) -> list[str]:
    """
    Generate n sub-queries for a claims question.

    Falls back to [question] if the LLM call fails or returns invalid output.
    """
    try:
        response = await litellm.acompletion(
            model=_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": _DECOMPOSE_PROMPT.format(question=question, n=n),
                }
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content or ""
        data = json.loads(_strip_fences(raw))
        queries = data.get("queries", [])
        if queries and all(isinstance(q, str) and q.strip() for q in queries):
            return [q.strip() for q in queries[:n]]
    except Exception as e:
        logger.warning("Query decomposition failed (%s); using original query", e)
    return [question]
