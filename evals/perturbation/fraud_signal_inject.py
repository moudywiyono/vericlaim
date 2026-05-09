"""
Fraud signal injection — synthetic fraud-positive claim generation.

Injects known-fraudulent patterns into base claims to create labeled fraud cases.
These are the ground-truth positives for Fraud Aggregator evaluation.
All injections are deterministic from spec.seed.
"""
from __future__ import annotations

from pathlib import Path

from evals.perturbation.base import Perturbation, PerturbationSpec


class StagedDamagePattern(Perturbation):
    """
    Inject EXIF timestamp manipulation: damage photo timestamps predate the
    incident date recorded in the manifest form_data.
    magnitude controls how many days earlier the EXIF timestamps appear.
    """

    @property
    def axis(self) -> str:
        return "staged_damage"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class VelocityAnomaly(Perturbation):
    """
    Inject cross-claim velocity signals: modify claim history metadata to show
    the same VIN appearing in multiple claims across multiple states.
    magnitude controls claim frequency (claims per 30-day window).
    """

    @property
    def axis(self) -> str:
        return "velocity_anomaly"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class NarrativeInconsistency(Perturbation):
    """
    Inject a specific factual contradiction between the verbal statement
    (audio transcript) and the police report (PDF field).
    magnitude maps to number of contradictions injected (1-3).
    These are labeled with known ground-truth for the Statement Analyst cross-ref eval.
    """

    @property
    def axis(self) -> str:
        return "narrative_inconsistency"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError
