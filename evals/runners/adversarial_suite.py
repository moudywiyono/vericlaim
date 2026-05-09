"""
Adversarial eval suite.

Covers three categories:
1. Prompt injection — adversarial instructions embedded in PDFs/forms
2. OOD claims — claim types the pipeline wasn't designed for
3. Demographic fairness probes — same claim, varied demographic-correlated features

Each subtest reports: detection rate, confabulation rate, and (for fairness) disparity score.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from evals.runners.base import SuiteResult

logger = logging.getLogger(__name__)


@dataclass
class AdversarialSubtestResult:
    name: str
    n_samples: int
    detection_rate: float | None = None    # for injection / OOD
    confabulation_rate: float | None = None
    disparity_score: float | None = None   # for fairness probes
    notes: str = ""


class AdversarialSuite:
    """
    Runs all adversarial subtests and aggregates results.

    Args:
        dataset_path: directory containing adversarial test cases,
                      organised as injection/, ood/, fairness/ subdirs
    """

    def __init__(self, dataset_path: Path) -> None:
        self.dataset_path = dataset_path

    def run(self) -> SuiteResult:
        """Run all adversarial subtests. Returns aggregated SuiteResult."""
        raise NotImplementedError

    def run_injection(self) -> AdversarialSubtestResult:
        """
        Test whether adversarial instructions in documents are followed.
        Before sanitization: detection_rate should be high.
        After sanitization: detection_rate should approach 0.
        """
        raise NotImplementedError

    def run_ood(self) -> AdversarialSubtestResult:
        """
        Submit out-of-distribution claims (marine cargo, crop insurance, etc.)
        Measure: does the system refuse/escalate, or does it confabulate?
        """
        raise NotImplementedError

    def run_fairness(self) -> AdversarialSubtestResult:
        """
        Hold claim facts constant; vary demographic-correlated features
        (name, zip code, accent proxy). Measure fraud score disparity.
        Reports honestly — this is a hard problem and acknowledging it is correct.
        """
        raise NotImplementedError
