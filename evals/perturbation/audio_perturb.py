"""
Audio perturbation axes: SNR degradation, background noise, accent variation.
Stubs — implementation in Phase 3 once Statement Analyst is built.
"""
from __future__ import annotations

from pathlib import Path

from evals.perturbation.base import Perturbation, PerturbationSpec


class SNRDegradation(Perturbation):
    """
    Add white Gaussian noise to target a specific SNR.
    magnitude=0.0 → SNR=40dB (clean)
    magnitude=1.0 → SNR=0dB (very noisy)
    """

    @property
    def axis(self) -> str:
        return "snr_degradation"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class BackgroundNoise(Perturbation):
    """
    Mix in real-world background noise (traffic, HVAC, crowd).
    magnitude=0.0 → no background noise
    magnitude=1.0 → background noise at -6dB relative to speech
    """

    @property
    def axis(self) -> str:
        return "background_noise"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class AccentVariation(Perturbation):
    """
    Resample audio through accent-varied TTS to test ASR robustness.
    magnitude maps to accent deviation score (accent corpus-dependent).
    """

    @property
    def axis(self) -> str:
        return "accent_variation"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError
