from __future__ import annotations

import json
from pathlib import Path

from ingestion.models import ClaimManifest, ClaimPacket


class ClaimLoadError(Exception):
    pass


class ClaimValidationError(Exception):
    pass


def load_claim_from_manifest(claim_dir: Path | str) -> ClaimPacket:
    """
    Load a claim from a directory containing manifest.json.
    All relative asset paths in the manifest are resolved to absolute Paths.
    """
    claim_dir = Path(claim_dir)
    manifest_path = claim_dir / "manifest.json"

    if not claim_dir.is_dir():
        raise ClaimLoadError(f"Claim directory does not exist: {claim_dir}")
    if not manifest_path.exists():
        raise ClaimLoadError(f"manifest.json not found in {claim_dir}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ClaimLoadError(f"Invalid JSON in manifest: {e}") from e

    try:
        manifest = ClaimManifest.model_validate(raw)
    except Exception as e:
        raise ClaimLoadError(f"manifest.json failed schema validation: {e}") from e

    return ClaimPacket(
        claim_id=manifest.claim_id,
        claim_dir=claim_dir,
        claim_type=manifest.claim_type,
        images=[claim_dir / p for p in manifest.images],
        pdfs=[claim_dir / p for p in manifest.pdfs],
        audio=[claim_dir / p for p in manifest.audio],
        form_data=manifest.form_data,
    )


def validate_claim_packet(packet: ClaimPacket) -> list[str]:
    """
    Validate that all asset paths referenced in the packet exist on disk.
    Returns a list of validation warnings (non-blocking).
    Raises ClaimValidationError for hard failures.
    """
    warnings: list[str] = []

    all_assets = [
        *[(p, "image") for p in packet.images],
        *[(p, "pdf") for p in packet.pdfs],
        *[(p, "audio") for p in packet.audio],
    ]

    for path, kind in all_assets:
        if not path.exists():
            warnings.append(f"Missing {kind} asset: {path}")
        elif not path.is_file():
            warnings.append(f"{kind} path is not a file: {path}")

    if not packet.form_data and not any(p.exists() for p, _ in all_assets):
        raise ClaimValidationError(
            f"Claim {packet.claim_id} has no form_data and no accessible assets — "
            "nothing to process."
        )

    return warnings
