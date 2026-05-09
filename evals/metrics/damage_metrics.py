"""
Damage Assessor evaluation metrics.

All functions are stubs with correct signatures. Implementations go in Phase 3
once the Damage Assessor is built and CarDD evaluation data is available.
"""
from __future__ import annotations


def mean_ap(
    predictions: list[dict],
    ground_truth: list[dict],
    iou_thresholds: list[float] | None = None,
) -> float:
    """
    Mean Average Precision for damage region detection.

    Args:
        predictions: list of {image_id, bbox, score, category}
        ground_truth: list of {image_id, bbox, category}
        iou_thresholds: IoU thresholds to average over.
                        Defaults to [0.5] for mAP@0.5; pass [0.5, 0.55, ..., 0.95] for COCO.
    Returns:
        mAP score in [0, 1]
    """
    raise NotImplementedError


def macro_f1_severity(
    predictions: list[str],
    ground_truth: list[str],
    labels: list[str] | None = None,
) -> float:
    """
    Macro-averaged F1 across severity categories: cosmetic / moderate / severe / total_loss.

    Uses macro averaging so rare severe/total_loss cases are not underweighted.

    Args:
        predictions: list of predicted severity labels
        ground_truth: list of ground-truth severity labels
        labels: severity label set (defaults to all four categories)
    Returns:
        macro-F1 in [0, 1]
    """
    raise NotImplementedError


def mape_by_damage_type(
    predictions: dict[str, list[float]],
    ground_truth: dict[str, list[float]],
) -> dict[str, float]:
    """
    Mean Absolute Percentage Error for cost estimates, bucketed by damage type.

    A 20% error on a $500 bumper scrape is acceptable; on a $40K total loss it is not.
    Bucketing exposes this difference rather than aggregating over all cases.

    Args:
        predictions: {damage_type: [estimated_cost_usd, ...]}
        ground_truth: {damage_type: [actual_cost_usd, ...]}
    Returns:
        {damage_type: mape_percent}
    """
    raise NotImplementedError


def grounding_fidelity(
    line_items: list[dict],
    bbox_annotations: list[dict],
) -> float:
    """
    Fraction of cost line items where the cited bounding box actually contains
    the described damage region (requires human-labeled slice).

    Args:
        line_items: list of {region_id, description, evidence_uri, bbox}
        bbox_annotations: list of {region_id, contains_described_damage: bool}
    Returns:
        fidelity score in [0, 1]
    """
    raise NotImplementedError
