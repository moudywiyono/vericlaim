"""Tests for document evaluation metrics."""
from __future__ import annotations

import pytest

from evals.metrics.document_metrics import _edit_distance, anls_score, field_exact_match


# ---------------------------------------------------------------------------
# field_exact_match
# ---------------------------------------------------------------------------

class TestFieldExactMatch:
    def test_perfect_match(self):
        preds = {"date_of_loss": "2024-03-15", "claimant_name": "John Smith"}
        gts = {"date_of_loss": "2024-03-15", "claimant_name": "John Smith"}
        assert field_exact_match(preds, gts) == 1.0

    def test_no_matches(self):
        preds = {"date_of_loss": "2024-01-01"}
        gts = {"date_of_loss": "2024-03-15"}
        assert field_exact_match(preds, gts) == 0.0

    def test_partial_match(self):
        preds = {"date_of_loss": "2024-03-15", "claimant_name": "WRONG"}
        gts = {"date_of_loss": "2024-03-15", "claimant_name": "John Smith"}
        assert field_exact_match(preds, gts) == 0.5

    def test_case_insensitive(self):
        preds = {"claimant_name": "JOHN SMITH"}
        gts = {"claimant_name": "john smith"}
        assert field_exact_match(preds, gts) == 1.0

    def test_whitespace_stripped(self):
        preds = {"policy_number": "  VC-001  "}
        gts = {"policy_number": "VC-001"}
        assert field_exact_match(preds, gts) == 1.0

    def test_missing_prediction_counts_as_miss(self):
        preds: dict = {}
        gts = {"date_of_loss": "2024-03-15"}
        assert field_exact_match(preds, gts) == 0.0

    def test_empty_ground_truth_returns_one(self):
        assert field_exact_match({"k": "v"}, {}) == 1.0

    def test_extra_predicted_fields_ignored(self):
        preds = {"date_of_loss": "2024-03-15", "extra_field": "irrelevant"}
        gts = {"date_of_loss": "2024-03-15"}
        assert field_exact_match(preds, gts) == 1.0


# ---------------------------------------------------------------------------
# anls_score
# ---------------------------------------------------------------------------

class TestANLSScore:
    def test_perfect_match(self):
        assert anls_score(["John Smith"], ["John Smith"]) == 1.0

    def test_completely_wrong_below_threshold(self):
        # Very dissimilar strings → NLS well below 0.5 → ANLS = 0
        assert anls_score(["XXXXXXXXXX"], ["John Smith"]) == 0.0

    def test_near_perfect_match_above_threshold(self):
        # One character substitution — should score > 0.5
        score = anls_score(["John Smyth"], ["John Smith"])
        assert score > 0.5

    def test_empty_inputs_returns_one(self):
        assert anls_score([], []) == 1.0

    def test_multiple_samples_averaged(self):
        # First perfect, second completely wrong → ~0.5
        score = anls_score(["John Smith", "XXXXXXXXXX"], ["John Smith", "John Smith"])
        assert 0.0 < score < 1.0

    def test_custom_threshold_zero_accepts_any_similarity(self):
        # Short fragment "Jo" vs "John Smith" — NLS is low but above 0
        default = anls_score(["Jo"], ["John Smith"])
        low_thresh = anls_score(["Jo"], ["John Smith"], threshold=0.0)
        assert low_thresh >= default

    def test_empty_ground_truth_string_with_no_prediction(self):
        assert anls_score([""], [""]) == 1.0

    def test_empty_ground_truth_string_with_prediction(self):
        assert anls_score(["something"], [""]) == 0.0


# ---------------------------------------------------------------------------
# _edit_distance
# ---------------------------------------------------------------------------

class TestEditDistance:
    def test_identical(self):
        assert _edit_distance("abc", "abc") == 0

    def test_both_empty(self):
        assert _edit_distance("", "") == 0

    def test_one_empty(self):
        assert _edit_distance("abc", "") == 3
        assert _edit_distance("", "abc") == 3

    def test_single_substitution(self):
        assert _edit_distance("cat", "bat") == 1

    def test_single_insertion(self):
        assert _edit_distance("abc", "abcd") == 1

    def test_single_deletion(self):
        assert _edit_distance("abcd", "abc") == 1

    def test_completely_different(self):
        assert _edit_distance("abc", "xyz") == 3
