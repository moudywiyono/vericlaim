"""
Perturbation pipeline base classes.

Every perturbation must be deterministic and reproducible from its spec.
Output paths follow: synthetic/{base_claim_id}/{axis}_{magnitude}_{seed}/

Usage:
    spec = PerturbationSpec(base_claim_id="claim-001", axis="jpeg_compression",
                            magnitude=0.3, seed=42)
    perturbed_dir = MyPerturbation().apply(source_dir, spec)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PerturbationSpec:
    base_claim_id: str
    axis: str
    magnitude: float  # 0.0 (no perturbation) .. 1.0 (maximum perturbation)
    seed: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.magnitude <= 1.0:
            raise ValueError(f"magnitude must be in [0, 1], got {self.magnitude}")

    def output_dir(self, synthetic_root: Path) -> Path:
        tag = f"{self.axis}_{self.magnitude:.2f}_{self.seed}"
        return synthetic_root / self.base_claim_id / tag


class Perturbation(ABC):
    """
    Base class for all perturbation types.

    Subclasses implement apply() to modify assets in source_dir and write
    results to the directory returned by spec.output_dir(synthetic_root).
    The output directory must contain a valid manifest.json.
    """

    @property
    @abstractmethod
    def axis(self) -> str:
        """Must match the PerturbationSpec.axis this class handles."""

    @abstractmethod
    def apply(self, source_dir: Path, spec: PerturbationSpec, synthetic_root: Path) -> Path:
        """
        Apply the perturbation to all relevant assets in source_dir.
        Write the perturbed claim (including manifest.json) to the output directory.
        Returns the output directory path.

        Must be deterministic: same spec + same source → same output.
        """
