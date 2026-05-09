"""
End-to-end eval runner.

Runs the full orchestration pipeline on labeled claims and measures
adjudication outcome accuracy.

The gold set (evals/datasets/e2e_gold/) is PROTECTED: this suite will not run
against it unless VERICLAIM_ALLOW_GOLD_EVAL=1 is set. Never iterate prompts
against the gold set — it exists only for final reporting.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from evals.runners.base import SuiteResult

logger = logging.getLogger(__name__)

_GOLD_DIR_NAME = "e2e_gold"


class GoldSetProtected(Exception):
    """Raised when attempting to run against the gold set without explicit opt-in."""


class E2ESuite:
    """
    Runs the full pipeline on a labeled eval dataset.

    Args:
        dataset_path: path to the eval dataset directory
    """

    def __init__(self, dataset_path: Path) -> None:
        self.dataset_path = dataset_path
        self._check_gold_gate()

    def _check_gold_gate(self) -> None:
        is_gold = _GOLD_DIR_NAME in self.dataset_path.parts
        if is_gold and not os.getenv("VERICLAIM_ALLOW_GOLD_EVAL"):
            raise GoldSetProtected(
                f"Refusing to run against gold set at {self.dataset_path}. "
                "Set VERICLAIM_ALLOW_GOLD_EVAL=1 only for final reporting runs. "
                "Use evals/datasets/synthetic/ during development."
            )

    def run(self) -> SuiteResult:
        """
        Run the full pipeline on all samples in dataset_path.

        For each sample:
        1. Run run_claim() end-to-end
        2. Compare adjudication output to gold label
        3. Compute: pairwise judge score, outcome accuracy, cost, latency

        Returns SuiteResult with all metrics populated.
        """
        raise NotImplementedError
