"""
Confidence calibration metrics.

When a model says it is 90% confident, it should be correct ~90% of the time.
ECE and reliability diagrams make this contract measurable.
Stubs — implementations in Phase 3 when specialist confidence scores are available.
"""
from __future__ import annotations


def expected_calibration_error(
    confidences: list[float],
    correctness: list[bool],
    n_bins: int = 10,
) -> float:
    """
    Expected Calibration Error (ECE) using equal-width bins.

    ECE = Σ_b (|B_b| / n) * |acc(B_b) - conf(B_b)|

    Args:
        confidences: predicted confidence scores in [0, 1]
        correctness: whether each prediction was correct
        n_bins: number of equal-width bins for calibration diagram
    Returns:
        ECE in [0, 1]; lower is better
    """
    raise NotImplementedError


def reliability_diagram(
    confidences: list[float],
    correctness: list[bool],
    n_bins: int = 10,
) -> dict[str, list[float]]:
    """
    Data for a reliability diagram (calibration curve).

    Args:
        confidences: predicted confidence scores
        correctness: whether each prediction was correct
        n_bins: number of equal-width bins
    Returns:
        {"bin_centers": [...], "mean_confidence": [...], "mean_accuracy": [...], "bin_counts": [...]}
        A perfectly calibrated model has mean_confidence ≈ mean_accuracy in every bin.
    """
    raise NotImplementedError
