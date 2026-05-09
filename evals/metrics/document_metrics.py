"""
Document Extractor evaluation metrics.

field_exact_match and anls_score are the primary metrics used in DocVQA-style
evaluation of structured field extraction from insurance documents.
"""
from __future__ import annotations


def field_exact_match(
    predictions: dict[str, str],
    ground_truth: dict[str, str],
) -> float:
    """
    Fraction of ground-truth fields whose predicted value exactly matches
    (case-insensitive, whitespace-stripped).

    Args:
        predictions: {field_name: predicted_value}
        ground_truth: {field_name: expected_value}
    Returns:
        exact match rate in [0, 1]
    """
    if not ground_truth:
        return 1.0
    matches = sum(
        1 for field, gt_val in ground_truth.items()
        if predictions.get(field, "").strip().lower() == gt_val.strip().lower()
    )
    return matches / len(ground_truth)


def anls_score(
    predictions: list[str],
    ground_truth: list[str],
    threshold: float = 0.5,
) -> float:
    """
    Average Normalized Levenshtein Similarity (ANLS) — the standard DocVQA metric.

    NLS values below `threshold` are clamped to 0 to penalise wild guesses while
    rewarding near-correct extractions (OCR noise, minor formatting differences).

    Args:
        predictions: list of predicted field values
        ground_truth: list of ground-truth field values
        threshold: NLS values below this are set to 0.0 (default 0.5 per DocVQA)
    Returns:
        mean ANLS in [0, 1]
    """
    if not ground_truth:
        return 1.0

    scores = []
    for pred, gt in zip(predictions, ground_truth):
        if not gt:
            scores.append(1.0 if not pred else 0.0)
            continue
        p, g = pred.strip().lower(), gt.strip().lower()
        dist = _edit_distance(p, g)
        nls = 1.0 - dist / max(len(p), len(g), 1)
        scores.append(nls if nls >= threshold else 0.0)

    return sum(scores) / len(scores)


def _edit_distance(s1: str, s2: str) -> int:
    """Wagner-Fischer edit distance (O(n) space)."""
    m, n = len(s1), len(s2)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if s1[i - 1] == s2[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]
