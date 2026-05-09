"""
Image perturbation axes: JPEG compression, motion blur, low-light, occlusion.

All classes are stubs with correct signatures. Implementation in Phase 3
once the Damage Assessor is built and we can measure mAP degradation curves.
"""
from __future__ import annotations

from pathlib import Path

from evals.perturbation.base import Perturbation, PerturbationSpec


class JPEGCompression(Perturbation):
    """
    Compress images to varying JPEG quality levels.
    magnitude=0.0 → quality=95 (near-lossless)
    magnitude=1.0 → quality=5 (severe compression)
    """

    @property
    def axis(self) -> str:
        return "jpeg_compression"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class MotionBlur(Perturbation):
    """
    Apply synthetic motion blur.
    magnitude=0.0 → kernel_size=1 (no blur)
    magnitude=1.0 → kernel_size=31
    """

    @property
    def axis(self) -> str:
        return "motion_blur"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class LowLight(Perturbation):
    """
    Simulate low-light by reducing gamma.
    magnitude=0.0 → no change
    magnitude=1.0 → very dark (gamma=0.2)
    """

    @property
    def axis(self) -> str:
        return "low_light"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class Occlusion(Perturbation):
    """
    Occlude a random percentage of each image with black rectangles.
    magnitude=0.0 → no occlusion
    magnitude=1.0 → 40% of pixels occluded
    """

    @property
    def axis(self) -> str:
        return "occlusion"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError
