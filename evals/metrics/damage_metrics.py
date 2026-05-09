"""
Damage Assessor evaluation metrics.

mean_ap and grounding_fidelity require labeled bounding-box ground truth
(CarDD dataset, Phase 3). macro_f1_severity and mape_by_damage_type are
computable once the Damage Assessor produces findings.
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
                        Defaults to [0.5] for mAP@0.5; pass COCO range for mAP@[0.5:0.95].
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

    Macro averaging prevents rare severe/total_loss cases from being underweighted.

    Args:
        predictions: list of predicted severity labels
        ground_truth: list of ground-truth severity labels
        labels: severity label set (defaults to all four categories)
    Returns:
        macro-F1 in [0, 1]
    """
    if labels is None:
        labels = ["cosmetic", "moderate", "severe", "total_loss"]
    if not predictions or not ground_truth:
        return 0.0

    f1_scores = []
    for label in labels:
        tp = sum(1 for p, g in zip(predictions, ground_truth) if p == label and g == label)
        fp = sum(1 for p, g in zip(predictions, ground_truth) if p == label and g != label)
        fn = sum(1 for p, g in zip(predictions, ground_truth) if p != label and g == label)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        f1_scores.append(f1)

    return sum(f1_scores) / len(f1_scores)


def mape_by_damage_type(
    predictions: dict[str, list[float]],
    ground_truth: dict[str, list[float]],
) -> dict[str, float]:
    """
    Mean Absolute Percentage Error for cost estimates, bucketed by damage type.

    Bucketing exposes that a 20% error on a $500 repair is very different from
    a 20% error on a $40K total loss — aggregating over all cases would mask this.

    Args:
        predictions: {damage_type: [estimated_cost_usd, ...]}
        ground_truth: {damage_type: [actual_cost_usd, ...]}
    Returns:
        {damage_type: mape_percent}
    """
    result: dict[str, float] = {}
    for damage_type, gt_values in ground_truth.items():
        pred_values = predictions.get(damage_type, [])
        pairs = list(zip(pred_values, gt_values))
        mapes = [abs(p - g) / g * 100.0 for p, g in pairs if g != 0.0]
        result[damage_type] = sum(mapes) / len(mapes) if mapes else 0.0
    return result


def grounding_fidelity(
    line_items: list[dict],
    bbox_annotations: list[dict],
) -> float:
    """
    Fraction of cost line items where the cited bounding box actually contains
    the described damage region (requires human-labeled slice from CarDD).

    Args:
        line_items: list of {region_id, description, evidence_uri, bbox}
        bbox_annotations: list of {region_id, contains_described_damage: bool}
    Returns:
        fidelity score in [0, 1]
    """
    raise NotImplementedError
