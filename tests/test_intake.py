import json
from pathlib import Path

import pytest

from ingestion.intake import ClaimLoadError, ClaimValidationError, load_claim_from_manifest, validate_claim_packet
from ingestion.models import ClaimPacket, ClaimType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_manifest(directory: Path, data: dict) -> None:
    (directory / "manifest.json").write_text(json.dumps(data), encoding="utf-8")


def minimal_manifest(claim_id: str = "test-001") -> dict:
    return {
        "claim_id": claim_id,
        "images": [],
        "pdfs": [],
        "audio": [],
        "form_data": {"description": "rear-end collision"},
    }


# ---------------------------------------------------------------------------
# load_claim_from_manifest — happy path
# ---------------------------------------------------------------------------

def test_load_returns_correct_claim_id(tmp_path: Path) -> None:
    write_manifest(tmp_path, minimal_manifest("abc-123"))
    packet = load_claim_from_manifest(tmp_path)
    assert packet.claim_id == "abc-123"


def test_load_resolves_asset_paths_to_absolute(tmp_path: Path) -> None:
    (tmp_path / "photo.jpg").write_bytes(b"fake")
    write_manifest(tmp_path, {**minimal_manifest(), "images": ["photo.jpg"]})
    packet = load_claim_from_manifest(tmp_path)
    assert packet.images[0] == tmp_path / "photo.jpg"
    assert packet.images[0].is_absolute()


def test_load_accepts_string_path(tmp_path: Path) -> None:
    write_manifest(tmp_path, minimal_manifest())
    packet = load_claim_from_manifest(str(tmp_path))
    assert packet.claim_id == "test-001"


def test_load_preserves_claim_type_from_manifest(tmp_path: Path) -> None:
    write_manifest(tmp_path, {**minimal_manifest(), "claim_type": "auto"})
    packet = load_claim_from_manifest(tmp_path)
    assert packet.claim_type == ClaimType.AUTO


def test_load_claim_type_none_when_absent(tmp_path: Path) -> None:
    write_manifest(tmp_path, minimal_manifest())
    packet = load_claim_from_manifest(tmp_path)
    assert packet.claim_type is None


def test_load_sets_claim_dir(tmp_path: Path) -> None:
    write_manifest(tmp_path, minimal_manifest())
    packet = load_claim_from_manifest(tmp_path)
    assert packet.claim_dir == tmp_path


def test_load_preserves_form_data(tmp_path: Path) -> None:
    data = minimal_manifest()
    data["form_data"] = {"incident_date": "2026-04-01", "amount": 1234.5}
    write_manifest(tmp_path, data)
    packet = load_claim_from_manifest(tmp_path)
    assert packet.form_data["incident_date"] == "2026-04-01"
    assert packet.form_data["amount"] == 1234.5


def test_load_multiple_assets(tmp_path: Path) -> None:
    for name in ["a.jpg", "b.jpg"]:
        (tmp_path / name).write_bytes(b"fake")
    (tmp_path / "report.pdf").write_bytes(b"fake")
    write_manifest(tmp_path, {
        **minimal_manifest(),
        "images": ["a.jpg", "b.jpg"],
        "pdfs": ["report.pdf"],
    })
    packet = load_claim_from_manifest(tmp_path)
    assert len(packet.images) == 2
    assert len(packet.pdfs) == 1


# ---------------------------------------------------------------------------
# load_claim_from_manifest — error cases
# ---------------------------------------------------------------------------

def test_load_raises_when_dir_missing() -> None:
    with pytest.raises(ClaimLoadError, match="does not exist"):
        load_claim_from_manifest(Path("/nonexistent/path/claim-xyz"))


def test_load_raises_when_manifest_missing(tmp_path: Path) -> None:
    with pytest.raises(ClaimLoadError, match="manifest.json not found"):
        load_claim_from_manifest(tmp_path)


def test_load_raises_on_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{ this is not json }", encoding="utf-8")
    with pytest.raises(ClaimLoadError, match="Invalid JSON"):
        load_claim_from_manifest(tmp_path)


def test_load_raises_on_missing_claim_id(tmp_path: Path) -> None:
    data = minimal_manifest()
    del data["claim_id"]
    write_manifest(tmp_path, data)
    with pytest.raises(ClaimLoadError, match="schema validation"):
        load_claim_from_manifest(tmp_path)


def test_load_raises_on_empty_claim_id(tmp_path: Path) -> None:
    write_manifest(tmp_path, {**minimal_manifest(), "claim_id": "   "})
    with pytest.raises(ClaimLoadError, match="schema validation"):
        load_claim_from_manifest(tmp_path)


def test_load_raises_on_invalid_claim_type(tmp_path: Path) -> None:
    write_manifest(tmp_path, {**minimal_manifest(), "claim_type": "marine"})
    with pytest.raises(ClaimLoadError, match="schema validation"):
        load_claim_from_manifest(tmp_path)


# ---------------------------------------------------------------------------
# validate_claim_packet
# ---------------------------------------------------------------------------

def test_validate_returns_no_warnings_for_clean_packet(tmp_path: Path) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"fake")
    write_manifest(tmp_path, {**minimal_manifest(), "images": ["photo.jpg"]})
    packet = load_claim_from_manifest(tmp_path)
    warnings = validate_claim_packet(packet)
    assert warnings == []


def test_validate_warns_on_missing_asset(tmp_path: Path) -> None:
    write_manifest(tmp_path, {**minimal_manifest(), "images": ["missing.jpg"]})
    packet = load_claim_from_manifest(tmp_path)
    warnings = validate_claim_packet(packet)
    assert len(warnings) == 1
    assert "missing.jpg" in warnings[0]


def test_validate_warns_on_multiple_missing_assets(tmp_path: Path) -> None:
    write_manifest(tmp_path, {
        **minimal_manifest(),
        "images": ["a.jpg", "b.jpg"],
        "pdfs": ["report.pdf"],
    })
    packet = load_claim_from_manifest(tmp_path)
    warnings = validate_claim_packet(packet)
    assert len(warnings) == 3


def test_validate_raises_when_nothing_to_process(tmp_path: Path) -> None:
    manifest = {"claim_id": "empty-001", "images": [], "pdfs": [], "audio": [], "form_data": {}}
    write_manifest(tmp_path, manifest)
    packet = load_claim_from_manifest(tmp_path)
    with pytest.raises(ClaimValidationError, match="nothing to process"):
        validate_claim_packet(packet)


def test_validate_no_raise_when_only_form_data(tmp_path: Path) -> None:
    write_manifest(tmp_path, minimal_manifest())
    packet = load_claim_from_manifest(tmp_path)
    # form_data has "description" — should not raise
    warnings = validate_claim_packet(packet)
    assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# ClaimPacket properties
# ---------------------------------------------------------------------------

def test_has_images_false_when_empty(tmp_path: Path) -> None:
    write_manifest(tmp_path, minimal_manifest())
    packet = load_claim_from_manifest(tmp_path)
    assert not packet.has_images


def test_has_images_true_when_present(tmp_path: Path) -> None:
    (tmp_path / "p.jpg").write_bytes(b"x")
    write_manifest(tmp_path, {**minimal_manifest(), "images": ["p.jpg"]})
    packet = load_claim_from_manifest(tmp_path)
    assert packet.has_images
