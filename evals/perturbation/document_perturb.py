"""
Document perturbation axes: scan resolution, page rotation, OCR noise.
Stubs — implementation in Phase 3 once Document Extractor is built.
"""
from __future__ import annotations

from pathlib import Path

from evals.perturbation.base import Perturbation, PerturbationSpec


class ScanResolution(Perturbation):
    """
    Downsample PDFs to simulate low-DPI scans.
    magnitude=0.0 → 300 DPI (clean)
    magnitude=1.0 → 72 DPI (very low quality)
    """

    @property
    def axis(self) -> str:
        return "scan_resolution"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class PageRotation(Perturbation):
    """
    Rotate document pages by random angles.
    magnitude=0.0 → 0° rotation
    magnitude=1.0 → up to ±15° rotation
    """

    @property
    def axis(self) -> str:
        return "page_rotation"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError


class OCRNoise(Perturbation):
    """
    Corrupt text in PDFs with OCR-style character substitutions.
    magnitude=0.0 → no corruption
    magnitude=1.0 → 10% character error rate
    """

    @property
    def axis(self) -> str:
        return "ocr_noise"

    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        raise NotImplementedError
