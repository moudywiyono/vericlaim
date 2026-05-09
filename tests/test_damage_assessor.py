"""Tests for DamageAssessorNode."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from ingestion.models import ClaimPacket, ClaimType
from orchestration.nodes.damage_assessor import DamageAssessorNode
from orchestration.state import AgentStatus, EvidenceStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _vlm_response(regions: list[dict], note: str = "") -> MagicMock:
    m = MagicMock()
    m.choices[0].message.content = json.dumps({"regions": regions, "note": note})
    return m


def _region(
    region_id: str = "front_bumper",
    category: str = "moderate",
    cost: float = 1500.0,
    confidence: float = 0.8,
) -> dict:
    return {
        "region_id": region_id,
        "category": category,
        "description": "Dent and paint damage",
        "location": "front bumper, left side",
        "estimated_cost_usd": cost,
        "cost_confidence": confidence,
    }


@pytest.fixture
def image_path(tmp_path: Path) -> Path:
    img = Image.new("RGB", (100, 100), color=(128, 64, 32))
    p = tmp_path / "damage.jpg"
    img.save(p)
    return p


@pytest.fixture
def packet(tmp_path: Path, image_path: Path) -> ClaimPacket:
    return ClaimPacket(
        claim_id="test-001",
        claim_dir=tmp_path,
        claim_type=ClaimType.AUTO,
        images=[image_path],
    )


# ---------------------------------------------------------------------------
# Node identity
# ---------------------------------------------------------------------------

def test_node_name():
    assert DamageAssessorNode().name == "damage_assessor"


def test_timeout_at_least_30s():
    assert DamageAssessorNode().timeout_s >= 30.0


# ---------------------------------------------------------------------------
# SKIPPED when no images
# ---------------------------------------------------------------------------

async def test_no_images_returns_skipped(tmp_path: Path):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")
    empty_packet = ClaimPacket(claim_id="test-001", claim_dir=tmp_path, images=[])
    result = await node.run(store, empty_packet)
    assert result.status == AgentStatus.SKIPPED
    assert result.store.specialist_status["damage_assessor"] == AgentStatus.SKIPPED
    assert result.store.damage_findings == []


# ---------------------------------------------------------------------------
# SUCCESS path
# ---------------------------------------------------------------------------

async def test_successful_single_image(packet: ClaimPacket):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")
    mock_resp = _vlm_response([_region()])

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.SUCCESS
    assert len(result.store.damage_findings) == 1
    f = result.store.damage_findings[0]
    assert f.region_id == "front_bumper"
    assert f.category == "moderate"
    assert f.estimated_cost_usd == 1500.0
    assert result.store.specialist_status["damage_assessor"] == AgentStatus.SUCCESS


async def test_evidence_uri_points_to_image(packet: ClaimPacket, image_path: Path):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_vlm_response([_region()])):
        result = await node.run(store, packet)

    uri = result.store.damage_findings[0].evidence_uri
    assert uri.startswith("file://")
    assert image_path.name in uri


async def test_multiple_regions_in_one_image(packet: ClaimPacket):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")
    regions = [
        _region("front_bumper", "moderate", 1500.0),
        _region("driver_door", "cosmetic", 300.0),
    ]

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_vlm_response(regions)):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.SUCCESS
    assert len(result.store.damage_findings) == 2


async def test_returns_only_new_findings(tmp_path: Path, image_path: Path):
    # Nodes return only their new findings; the orchestrator owns accumulation.
    from orchestration.state import DamageFinding
    node = DamageAssessorNode()
    pre_existing = DamageFinding(
        region_id="pre_existing",
        category="cosmetic",
        description="prior finding",
        estimated_cost_usd=100.0,
        cost_confidence=0.5,
        evidence_uri="file:///prior",
    )
    store = EvidenceStore(claim_id="test-001", damage_findings=[pre_existing])
    packet = ClaimPacket(claim_id="test-001", claim_dir=tmp_path, images=[image_path])

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_vlm_response([_region()])):
        result = await node.run(store, packet)

    # result store contains only the 1 new finding, not the pre-existing one
    assert len(result.store.damage_findings) == 1
    assert result.store.damage_findings[0].region_id != "pre_existing"


# ---------------------------------------------------------------------------
# PARTIAL path
# ---------------------------------------------------------------------------

async def test_partial_when_some_images_fail(tmp_path: Path, image_path: Path):
    bad_path = tmp_path / "bad.jpg"
    bad_path.write_bytes(b"irrelevant")

    packet = ClaimPacket(
        claim_id="test-002", claim_dir=tmp_path,
        images=[image_path, bad_path],
    )
    store = EvidenceStore(claim_id="test-002")
    node = DamageAssessorNode()

    call_count = 0

    async def mock_acompletion(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _vlm_response([_region()])
        raise Exception("API error on second image")

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.PARTIAL
    assert len(result.store.damage_findings) == 1


async def test_partial_when_empty_regions_returned(packet: ClaimPacket):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")

    with patch(
        "litellm.acompletion", new_callable=AsyncMock,
        return_value=_vlm_response([], note="Image too blurry"),
    ):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.PARTIAL
    assert result.store.damage_findings == []


# ---------------------------------------------------------------------------
# FAILED path
# ---------------------------------------------------------------------------

async def test_failed_when_all_images_fail(tmp_path: Path, image_path: Path):
    packet = ClaimPacket(claim_id="test-003", claim_dir=tmp_path, images=[image_path])
    store = EvidenceStore(claim_id="test-003")
    node = DamageAssessorNode()

    with patch("litellm.acompletion", side_effect=Exception("API down")):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.FAILED
    assert result.store.specialist_status["damage_assessor"] == AgentStatus.FAILED


# ---------------------------------------------------------------------------
# Parse retry
# ---------------------------------------------------------------------------

async def test_malformed_json_retried(packet: ClaimPacket):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")

    bad = MagicMock()
    bad.choices[0].message.content = "not valid json {{ }}"
    good = _vlm_response([_region()])

    call_count = 0

    async def mock_acompletion(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return bad if call_count == 1 else good

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.SUCCESS
    assert call_count == 2


async def test_markdown_fenced_json_parsed(packet: ClaimPacket):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")

    fenced = MagicMock()
    fenced.choices[0].message.content = (
        '```json\n'
        + json.dumps({"regions": [_region("door", "severe", 8000.0)], "note": ""})
        + '\n```'
    )

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fenced):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.SUCCESS
    assert result.store.damage_findings[0].category == "severe"


# ---------------------------------------------------------------------------
# Degraded context
# ---------------------------------------------------------------------------

async def test_degraded_context_injected_into_prompt(packet: ClaimPacket):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")
    degraded = {"document_extractor": "document_extractor failed — do not reference document findings"}

    captured: list[dict] = []

    async def capture(*args, **kwargs):
        captured.extend(kwargs.get("messages", []))
        return _vlm_response([_region()])

    with patch("litellm.acompletion", side_effect=capture):
        await node.run(store, packet, degraded_context=degraded)

    all_content = json.dumps(captured)
    assert "document_extractor" in all_content


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

async def test_cost_usd_non_negative(packet: ClaimPacket):
    node = DamageAssessorNode()
    store = EvidenceStore(claim_id="test-001")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_vlm_response([_region()])):
        result = await node.run(store, packet)

    assert result.cost_usd >= 0.0
