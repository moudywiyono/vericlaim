import os
from pathlib import Path

import pytest

from evals.perturbation.base import Perturbation, PerturbationSpec
from evals.runners.e2e_suite import E2ESuite, GoldSetProtected


# ---------------------------------------------------------------------------
# PerturbationSpec — validation
# ---------------------------------------------------------------------------

def test_perturbation_spec_valid() -> None:
    spec = PerturbationSpec(
        base_claim_id="claim-001",
        axis="jpeg_compression",
        magnitude=0.5,
        seed=42,
    )
    assert spec.magnitude == 0.5
    assert spec.seed == 42


def test_perturbation_spec_magnitude_zero_valid() -> None:
    spec = PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=0.0, seed=0)
    assert spec.magnitude == 0.0


def test_perturbation_spec_magnitude_one_valid() -> None:
    spec = PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=1.0, seed=0)
    assert spec.magnitude == 1.0


def test_perturbation_spec_magnitude_below_zero_raises() -> None:
    with pytest.raises(ValueError, match="magnitude"):
        PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=-0.01, seed=0)


def test_perturbation_spec_magnitude_above_one_raises() -> None:
    with pytest.raises(ValueError, match="magnitude"):
        PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=1.01, seed=0)


# ---------------------------------------------------------------------------
# PerturbationSpec.output_dir — determinism
# ---------------------------------------------------------------------------

def test_output_dir_is_deterministic(tmp_path: Path) -> None:
    spec = PerturbationSpec(base_claim_id="c-001", axis="jpeg_compression", magnitude=0.3, seed=42)
    assert spec.output_dir(tmp_path) == spec.output_dir(tmp_path)


def test_output_dir_differs_by_magnitude(tmp_path: Path) -> None:
    spec_a = PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=0.3, seed=42)
    spec_b = PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=0.7, seed=42)
    assert spec_a.output_dir(tmp_path) != spec_b.output_dir(tmp_path)


def test_output_dir_differs_by_seed(tmp_path: Path) -> None:
    spec_a = PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=0.5, seed=1)
    spec_b = PerturbationSpec(base_claim_id="c-001", axis="blur", magnitude=0.5, seed=2)
    assert spec_a.output_dir(tmp_path) != spec_b.output_dir(tmp_path)


def test_output_dir_differs_by_base_claim(tmp_path: Path) -> None:
    spec_a = PerturbationSpec(base_claim_id="claim-001", axis="blur", magnitude=0.5, seed=1)
    spec_b = PerturbationSpec(base_claim_id="claim-002", axis="blur", magnitude=0.5, seed=1)
    assert spec_a.output_dir(tmp_path) != spec_b.output_dir(tmp_path)


def test_output_dir_is_under_base_claim_subdir(tmp_path: Path) -> None:
    spec = PerturbationSpec(base_claim_id="claim-007", axis="ocr_noise", magnitude=0.2, seed=99)
    output = spec.output_dir(tmp_path)
    assert output.parts[-2] == "claim-007"


def test_output_dir_tag_contains_axis_magnitude_seed(tmp_path: Path) -> None:
    spec = PerturbationSpec(base_claim_id="c-001", axis="snr_degradation", magnitude=0.6, seed=7)
    tag = spec.output_dir(tmp_path).name
    assert "snr_degradation" in tag
    assert "0.60" in tag
    assert "7" in tag


# ---------------------------------------------------------------------------
# Perturbation stubs — correct signatures
# ---------------------------------------------------------------------------

def test_image_perturbation_stubs_have_correct_axes() -> None:
    from evals.perturbation.image_perturb import (
        JPEGCompression,
        LowLight,
        MotionBlur,
        Occlusion,
    )
    assert JPEGCompression().axis == "jpeg_compression"
    assert MotionBlur().axis == "motion_blur"
    assert LowLight().axis == "low_light"
    assert Occlusion().axis == "occlusion"


def test_audio_perturbation_stubs_have_correct_axes() -> None:
    from evals.perturbation.audio_perturb import BackgroundNoise, SNRDegradation
    assert SNRDegradation().axis == "snr_degradation"
    assert BackgroundNoise().axis == "background_noise"


def test_document_perturbation_stubs_have_correct_axes() -> None:
    from evals.perturbation.document_perturb import OCRNoise, PageRotation, ScanResolution
    assert ScanResolution().axis == "scan_resolution"
    assert PageRotation().axis == "page_rotation"
    assert OCRNoise().axis == "ocr_noise"


def test_fraud_signal_stubs_have_correct_axes() -> None:
    from evals.perturbation.fraud_signal_inject import (
        NarrativeInconsistency,
        StagedDamagePattern,
        VelocityAnomaly,
    )
    assert StagedDamagePattern().axis == "staged_damage"
    assert VelocityAnomaly().axis == "velocity_anomaly"
    assert NarrativeInconsistency().axis == "narrative_inconsistency"


def test_all_perturbation_stubs_raise_not_implemented(tmp_path: Path) -> None:
    from evals.perturbation.image_perturb import JPEGCompression

    spec = PerturbationSpec(base_claim_id="c-001", axis="jpeg_compression", magnitude=0.5, seed=1)
    with pytest.raises(NotImplementedError):
        JPEGCompression().apply(tmp_path, spec, tmp_path)


# ---------------------------------------------------------------------------
# E2ESuite gold set gate
# ---------------------------------------------------------------------------

def test_gold_set_gate_blocks_without_env_var(tmp_path: Path) -> None:
    gold_dir = tmp_path / "e2e_gold"
    gold_dir.mkdir()
    with pytest.raises(GoldSetProtected):
        E2ESuite(gold_dir)


def test_gold_set_gate_allows_with_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERICLAIM_ALLOW_GOLD_EVAL", "1")
    gold_dir = tmp_path / "e2e_gold"
    gold_dir.mkdir()
    suite = E2ESuite(gold_dir)  # should not raise
    assert suite.dataset_path == gold_dir


def test_non_gold_dataset_never_blocked(tmp_path: Path) -> None:
    synthetic_dir = tmp_path / "synthetic"
    synthetic_dir.mkdir()
    suite = E2ESuite(synthetic_dir)  # should not raise regardless of env var
    assert suite.dataset_path == synthetic_dir


def test_gold_set_gate_checks_path_component(tmp_path: Path) -> None:
    # A path that contains "e2e_gold" somewhere in it should be blocked
    gold_dir = tmp_path / "datasets" / "e2e_gold" / "subset"
    gold_dir.mkdir(parents=True)
    with pytest.raises(GoldSetProtected):
        E2ESuite(gold_dir)


# ---------------------------------------------------------------------------
# Metric stubs all raise NotImplementedError
# ---------------------------------------------------------------------------

def test_metric_stubs_raise_not_implemented() -> None:
    from evals.metrics.calibration import expected_calibration_error, reliability_diagram
    from evals.metrics.damage_metrics import (
        grounding_fidelity,
        macro_f1_severity,
        mape_by_damage_type,
        mean_ap,
    )
    from evals.metrics.rag_metrics import (
        endorsement_attachment_rate,
        faithfulness_score,
        mean_reciprocal_rank,
        recall_at_k,
    )

    # macro_f1_severity and mape_by_damage_type are implemented in Phase 2
    stubs = [
        lambda: mean_ap([], []),
        lambda: grounding_fidelity([], []),
        lambda: recall_at_k([], [], k=5),
        lambda: mean_reciprocal_rank([], []),
        lambda: faithfulness_score([], []),
        lambda: endorsement_attachment_rate([], {}),
        lambda: expected_calibration_error([], []),
        lambda: reliability_diagram([], []),
    ]
    for stub in stubs:
        with pytest.raises(NotImplementedError):
            stub()
