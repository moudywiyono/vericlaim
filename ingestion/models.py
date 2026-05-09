from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class ClaimType(str, Enum):
    AUTO = "auto"
    PROPERTY = "property"
    LIABILITY = "liability"
    HEALTH = "health"
    UNKNOWN = "unknown"


class ClaimManifest(BaseModel):
    """
    On-disk representation of an incoming claim.
    A claim is a directory; this JSON lives at <dir>/manifest.json.
    """

    claim_id: str
    claim_type: ClaimType | None = None
    images: list[str] = Field(default_factory=list)  # relative paths within the claim dir
    pdfs: list[str] = Field(default_factory=list)
    audio: list[str] = Field(default_factory=list)
    form_data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("claim_id")
    @classmethod
    def claim_id_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim_id must not be empty")
        return v


class ClaimPacket(BaseModel):
    """
    Resolved claim with absolute Paths, ready for the orchestrator.
    Created by intake.load_claim_from_manifest().
    """

    claim_id: str
    claim_dir: Path
    claim_type: ClaimType | None = None
    images: list[Path] = Field(default_factory=list)
    pdfs: list[Path] = Field(default_factory=list)
    audio: list[Path] = Field(default_factory=list)
    form_data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def has_images(self) -> bool:
        return len(self.images) > 0

    @property
    def has_pdfs(self) -> bool:
        return len(self.pdfs) > 0

    @property
    def has_audio(self) -> bool:
        return len(self.audio) > 0


class RoutingDecision(BaseModel):
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)
    source: str  # "hf" | "llm" | "form_data"
