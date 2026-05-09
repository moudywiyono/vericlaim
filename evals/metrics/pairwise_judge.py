"""
LLM-as-judge in pairwise comparison mode.

Pairwise is significantly more reliable than absolute scoring for fuzzy tasks
(adjudication quality, settlement letter quality). The judge must be validated
against a human-labeled gold set before its scores are reported — if judge/human
agreement is below 80%, the judge is the bottleneck.
"""
from __future__ import annotations

from enum import Enum


class Preference(str, Enum):
    A = "A"
    B = "B"
    TIE = "tie"


class PairwiseJudge:
    """
    Compares two adjudication outputs and returns a preference.

    Args:
        model: LiteLLM model string for the judge LLM.
               Should be a strong reasoner (e.g. claude-sonnet-4-6 or gpt-4o).
    """

    def __init__(self, model: str) -> None:
        self.model = model

    def compare(
        self,
        output_a: str,
        output_b: str,
        context: str,
        criteria: list[str] | None = None,
    ) -> Preference:
        """
        Compare two adjudication outputs against a set of criteria.

        Args:
            output_a: first adjudication text
            output_b: second adjudication text
            context: the claim context (EvidenceStore summary) both outputs were generated from
            criteria: evaluation criteria (defaults to coverage accuracy, citation quality,
                      reasoning clarity, appropriate escalation)
        Returns:
            Preference.A / Preference.B / Preference.TIE
        """
        raise NotImplementedError

    def validate_against_gold(
        self,
        gold_pairs: list[dict],
    ) -> float:
        """
        Measure judge agreement with human-labeled gold pairs.

        Args:
            gold_pairs: list of {output_a, output_b, context, human_preference}
        Returns:
            agreement rate in [0, 1]; must exceed 0.80 before judge scores are reportable
        """
        raise NotImplementedError
