"""Tests for ComponentSuite eval runner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas

from evals.runners.component_suite import ComponentSuite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vlm_damage_response(regions: list[dict]) -> MagicMock:
    m = MagicMock()
    m.choices[0].message.content = json.dumps({"regions": regions, "note": ""})
    return m


def _llm_doc_response(fields: list[dict]) -> MagicMock:
    m = MagicMock()
    m.choices[0].message.content = json.dumps({
        "document_type": "claim_form",
        "fields": fields,
        "note": "",
    })
    return m


def _make_damage_sample(
    base: Path, claim_id: str, ground_truth: dict, with_image: bool = True
) -> Path:
    sample = base / claim_id
    sample.mkdir(parents=True)
    manifest = {
        "claim_id": claim_id,
        "claim_type": "auto",
        "images": ["damage.jpg"] if with_image else [],
        "pdfs": [],
        "audio": [],
        "form_data": {},
    }
    (sample / "manifest.json").write_text(json.dumps(manifest))
    if with_image:
        img = Image.new("RGB", (50, 50), color=(100, 50, 25))
        img.save(sample / "damage.jpg")
    (sample / "ground_truth.json").write_text(json.dumps(ground_truth))
    return sample


def _make_doc_sample(base: Path, claim_id: str, ground_truth: dict) -> Path:
    sample = base / claim_id
    sample.mkdir(parents=True)
    manifest = {
        "claim_id": claim_id,
        "claim_type": "auto",
        "images": [],
        "pdfs": ["report.pdf"],
        "audio": [],
        "form_data": {},
    }
    (sample / "manifest.json").write_text(json.dumps(manifest))
    c = rl_canvas.Canvas(str(sample / "report.pdf"))
    # Enough text to exceed _MIN_TEXT_CHARS=100
    lines = [
        "VERICLAIM MUTUAL — POLICE INCIDENT REPORT",
        "Date of Loss: 2024-03-15",
        "Report Date: 2024-03-16",
        "Claimant: Jane Doe",
        "Policy Number: VC-2024-009999",
        "Vehicle: 2021 Honda Civic sedan",
        "Incident: Minor rear-end collision at low speed on Highway 1.",
    ]
    for i, line in enumerate(lines):
        c.drawString(72, 750 - i * 20, line)
    c.save()
    (sample / "ground_truth.json").write_text(json.dumps(ground_truth))
    return sample


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_invalid_agent_name_raises():
    with pytest.raises(ValueError, match="Unknown agent"):
        ComponentSuite(agent_name="nonexistent", dataset_path=Path("/tmp"))


def test_empty_dataset_raises(tmp_path: Path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    suite = ComponentSuite(agent_name="damage_assessor", dataset_path=dataset)
    with pytest.raises(ValueError, match="No samples"):
        suite.run()


def test_unimplemented_agent_get_node_raises(tmp_path: Path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _make_damage_sample(dataset, "s001", {}, with_image=False)
    suite = ComponentSuite(agent_name="adjudicator", dataset_path=dataset)
    with pytest.raises(NotImplementedError):
        suite.run()


# ---------------------------------------------------------------------------
# Damage assessor suite
# ---------------------------------------------------------------------------

def test_damage_suite_returns_suite_result(tmp_path: Path):
    dataset = tmp_path / "dataset"
    gt = {
        "expected_categories": ["moderate"],
        "expected_cost_by_region": {"front_bumper": 1200.0},
    }
    _make_damage_sample(dataset, "s001", gt)

    suite = ComponentSuite(agent_name="damage_assessor", dataset_path=dataset)
    mock_resp = _vlm_damage_response([{
        "region_id": "front_bumper",
        "category": "moderate",
        "description": "Dent",
        "location": "front",
        "estimated_cost_usd": 1300.0,
        "cost_confidence": 0.8,
    }])

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = suite.run()

    assert result.n_samples == 1
    assert result.n_failures == 0
    assert result.suite_name == "damage_assessor_component_eval"
    assert "macro_f1_severity" in result.metrics
    # macro-F1 averages over 4 severity labels; with only "moderate" present, perfect
    # prediction on that label yields 1/4 = 0.25 (other three labels contribute 0)
    assert result.metrics["macro_f1_severity"] == pytest.approx(0.25)


def test_damage_suite_mape_metric_present(tmp_path: Path):
    dataset = tmp_path / "dataset"
    gt = {"expected_cost_by_region": {"front_bumper": 1200.0}}
    _make_damage_sample(dataset, "s001", gt)

    suite = ComponentSuite(agent_name="damage_assessor", dataset_path=dataset)
    mock_resp = _vlm_damage_response([{
        "region_id": "front_bumper",
        "category": "moderate",
        "description": "Dent",
        "location": "front",
        "estimated_cost_usd": 1200.0,
        "cost_confidence": 0.8,
    }])

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = suite.run()

    assert "mape_cost" in result.metrics
    assert result.metrics["mape_cost"] == 0.0  # perfect estimate


def test_damage_suite_counts_api_failures(tmp_path: Path):
    dataset = tmp_path / "dataset"
    _make_damage_sample(dataset, "s001", {})

    suite = ComponentSuite(agent_name="damage_assessor", dataset_path=dataset)

    with patch("litellm.acompletion", side_effect=Exception("API down")):
        result = suite.run()

    assert result.n_failures == 1


def test_damage_suite_multiple_samples_averaged(tmp_path: Path):
    dataset = tmp_path / "dataset"
    gt = {"expected_categories": ["moderate"]}
    _make_damage_sample(dataset, "s001", gt)
    _make_damage_sample(dataset, "s002", gt)

    suite = ComponentSuite(agent_name="damage_assessor", dataset_path=dataset)
    mock_resp = _vlm_damage_response([{
        "region_id": "r1", "category": "moderate", "description": "d",
        "location": "front", "estimated_cost_usd": 100.0, "cost_confidence": 0.8,
    }])

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = suite.run()

    assert result.n_samples == 2
    assert result.metrics["macro_f1_severity"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Document extractor suite
# ---------------------------------------------------------------------------

def test_doc_suite_field_exact_match(tmp_path: Path):
    dataset = tmp_path / "dataset"
    gt = {"expected_fields": {"date_of_loss": "2024-03-15", "claimant_name": "Jane Doe"}}
    _make_doc_sample(dataset, "s001", gt)

    suite = ComponentSuite(agent_name="document_extractor", dataset_path=dataset)
    mock_resp = _llm_doc_response([
        {"field_name": "date_of_loss", "value": "2024-03-15", "confidence": 0.95},
        {"field_name": "claimant_name", "value": "Jane Doe", "confidence": 0.9},
    ])

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = suite.run()

    assert result.metrics["field_exact_match"] == 1.0
    assert result.metrics["anls"] >= 0.9


def test_doc_suite_partial_extraction_scores_below_one(tmp_path: Path):
    dataset = tmp_path / "dataset"
    gt = {"expected_fields": {"date_of_loss": "2024-03-15", "claimant_name": "Jane Doe"}}
    _make_doc_sample(dataset, "s001", gt)

    suite = ComponentSuite(agent_name="document_extractor", dataset_path=dataset)
    mock_resp = _llm_doc_response([
        {"field_name": "date_of_loss", "value": "2024-03-15", "confidence": 0.95},
        # claimant_name is missing
    ])

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = suite.run()

    assert result.metrics["field_exact_match"] == 0.5


# ---------------------------------------------------------------------------
# SuiteResult shape
# ---------------------------------------------------------------------------

def test_suite_result_latency_fields_present(tmp_path: Path):
    dataset = tmp_path / "dataset"
    _make_damage_sample(dataset, "s001", {})

    suite = ComponentSuite(agent_name="damage_assessor", dataset_path=dataset)

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_vlm_damage_response([])):
        result = suite.run()

    assert result.latency_p50_ms >= 0
    assert result.latency_p95_ms >= 0
    assert result.dataset_path == dataset
