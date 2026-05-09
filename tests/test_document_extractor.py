"""Tests for DocumentExtractorNode."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from reportlab.pdfgen import canvas as rl_canvas

from ingestion.models import ClaimPacket, ClaimType
from orchestration.nodes.document_extractor import DocumentExtractorNode
from orchestration.state import AgentStatus, EvidenceStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _llm_response(fields: list[dict], doc_type: str = "claim_form", note: str = "") -> MagicMock:
    m = MagicMock()
    m.choices[0].message.content = json.dumps({
        "document_type": doc_type,
        "fields": fields,
        "note": note,
    })
    return m


def _field(name: str, value: str, confidence: float = 0.9) -> dict:
    return {"field_name": name, "value": value, "confidence": confidence}


def _make_pdf(path: Path, lines: list[str]) -> Path:
    c = rl_canvas.Canvas(str(path))
    y = 750
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return path


@pytest.fixture
def pdf_path(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "report.pdf", [
        "POLICE INCIDENT REPORT",
        "Date of Loss: 2024-03-15",
        "Claimant: John Smith",
        "Policy Number: VC-2024-001234",
        "Vehicle: 2022 Toyota Camry",
        "Incident: Rear-end collision at low speed near Main St.",
    ])


@pytest.fixture
def packet(tmp_path: Path, pdf_path: Path) -> ClaimPacket:
    return ClaimPacket(
        claim_id="doc-001",
        claim_dir=tmp_path,
        claim_type=ClaimType.AUTO,
        pdfs=[pdf_path],
    )


# ---------------------------------------------------------------------------
# Node identity
# ---------------------------------------------------------------------------

def test_node_name():
    assert DocumentExtractorNode().name == "document_extractor"


def test_timeout_at_least_30s():
    assert DocumentExtractorNode().timeout_s >= 30.0


# ---------------------------------------------------------------------------
# SKIPPED when no PDFs
# ---------------------------------------------------------------------------

async def test_no_pdfs_returns_skipped(tmp_path: Path):
    node = DocumentExtractorNode()
    store = EvidenceStore(claim_id="doc-001")
    empty_packet = ClaimPacket(claim_id="doc-001", claim_dir=tmp_path, pdfs=[])
    result = await node.run(store, empty_packet)
    assert result.status == AgentStatus.SKIPPED
    assert result.store.document_findings == []


# ---------------------------------------------------------------------------
# SUCCESS path
# ---------------------------------------------------------------------------

async def test_successful_field_extraction(packet: ClaimPacket):
    node = DocumentExtractorNode()
    store = EvidenceStore(claim_id="doc-001")
    fields = [
        _field("date_of_loss", "2024-03-15"),
        _field("claimant_name", "John Smith"),
        _field("policy_number", "VC-2024-001234"),
    ]
    mock_resp = _llm_response(fields, doc_type="police_report")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.SUCCESS
    assert len(result.store.document_findings) == 3
    field_map = {f.field_name: f.value for f in result.store.document_findings}
    assert field_map["date_of_loss"] == "2024-03-15"
    assert field_map["claimant_name"] == "John Smith"
    assert result.store.specialist_status["document_extractor"] == AgentStatus.SUCCESS


async def test_finding_has_correct_page_and_bbox(packet: ClaimPacket):
    node = DocumentExtractorNode()
    store = EvidenceStore(claim_id="doc-001")

    with patch(
        "litellm.acompletion", new_callable=AsyncMock,
        return_value=_llm_response([_field("date_of_loss", "2024-03-15")]),
    ):
        result = await node.run(store, packet)

    f = result.store.document_findings[0]
    assert f.page == 1
    assert f.bbox == (0.0, 0.0, 1.0, 1.0)  # full-page placeholder


async def test_returns_only_new_findings(tmp_path: Path, pdf_path: Path):
    # Nodes return only their new findings; the orchestrator owns accumulation.
    from orchestration.state import DocumentFinding
    node = DocumentExtractorNode()
    pre = DocumentFinding(
        field_name="prior_field", value="prior_value",
        page=1, bbox=(0.0, 0.0, 1.0, 1.0), extraction_confidence=0.5,
    )
    store = EvidenceStore(claim_id="doc-001", document_findings=[pre])
    packet = ClaimPacket(claim_id="doc-001", claim_dir=tmp_path, pdfs=[pdf_path])

    with patch(
        "litellm.acompletion", new_callable=AsyncMock,
        return_value=_llm_response([_field("date_of_loss", "2024-03-15")]),
    ):
        result = await node.run(store, packet)

    # result store contains only the 1 new finding, not the pre-existing one
    assert len(result.store.document_findings) == 1
    assert result.store.document_findings[0].field_name != "prior_field"


# ---------------------------------------------------------------------------
# PARTIAL path
# ---------------------------------------------------------------------------

async def test_partial_when_some_pdfs_fail(tmp_path: Path, pdf_path: Path):
    bad_path = tmp_path / "corrupt.pdf"
    bad_path.write_bytes(b"not a pdf")

    packet = ClaimPacket(
        claim_id="doc-002", claim_dir=tmp_path, pdfs=[pdf_path, bad_path],
    )
    store = EvidenceStore(claim_id="doc-002")
    node = DocumentExtractorNode()

    call_count = 0

    async def mock_acompletion(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _llm_response([_field("date_of_loss", "2024-03-15")])

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.PARTIAL


async def test_partial_when_pdf_has_sparse_text(tmp_path: Path):
    """A scanned PDF with no extractable text → sparse page → PARTIAL."""
    scan_path = tmp_path / "scan.pdf"
    c = rl_canvas.Canvas(str(scan_path))
    c.save()  # empty page — no text at all

    packet = ClaimPacket(claim_id="doc-003", claim_dir=tmp_path, pdfs=[scan_path])
    store = EvidenceStore(claim_id="doc-003")
    node = DocumentExtractorNode()

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        result = await node.run(store, packet)

    mock_llm.assert_not_called()  # sparse page skipped before LLM call
    assert result.status == AgentStatus.PARTIAL


# ---------------------------------------------------------------------------
# FAILED path
# ---------------------------------------------------------------------------

async def test_failed_when_all_pdfs_fail(tmp_path: Path):
    bad_path = tmp_path / "corrupt.pdf"
    bad_path.write_bytes(b"not a pdf")
    packet = ClaimPacket(claim_id="doc-004", claim_dir=tmp_path, pdfs=[bad_path])
    store = EvidenceStore(claim_id="doc-004")
    node = DocumentExtractorNode()

    result = await node.run(store, packet)
    assert result.status == AgentStatus.FAILED


# ---------------------------------------------------------------------------
# Parse retry
# ---------------------------------------------------------------------------

async def test_malformed_json_retried(packet: ClaimPacket):
    node = DocumentExtractorNode()
    store = EvidenceStore(claim_id="doc-001")

    bad = MagicMock()
    bad.choices[0].message.content = "not valid json {{ }}"
    good = _llm_response([_field("date_of_loss", "2024-03-15")])

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
    node = DocumentExtractorNode()
    store = EvidenceStore(claim_id="doc-001")

    fenced = MagicMock()
    fenced.choices[0].message.content = (
        "```json\n"
        + json.dumps({
            "document_type": "repair_estimate",
            "fields": [_field("estimated_repair_cost", "4500.00")],
            "note": "",
        })
        + "\n```"
    )

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=fenced):
        result = await node.run(store, packet)

    assert result.status == AgentStatus.SUCCESS
    assert result.store.document_findings[0].field_name == "estimated_repair_cost"


# ---------------------------------------------------------------------------
# Degraded context
# ---------------------------------------------------------------------------

async def test_degraded_context_injected_into_prompt(packet: ClaimPacket):
    node = DocumentExtractorNode()
    store = EvidenceStore(claim_id="doc-001")
    degraded = {"damage_assessor": "damage_assessor failed — do not reference damage findings"}

    captured: list[dict] = []

    async def capture(*args, **kwargs):
        captured.extend(kwargs.get("messages", []))
        return _llm_response([_field("date_of_loss", "2024-03-15")])

    with patch("litellm.acompletion", side_effect=capture):
        await node.run(store, packet, degraded_context=degraded)

    all_content = json.dumps(captured)
    assert "damage_assessor" in all_content


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

async def test_cost_usd_non_negative(packet: ClaimPacket):
    node = DocumentExtractorNode()
    store = EvidenceStore(claim_id="doc-001")

    with patch(
        "litellm.acompletion", new_callable=AsyncMock,
        return_value=_llm_response([_field("date_of_loss", "2024-03-15")]),
    ):
        result = await node.run(store, packet)

    assert result.cost_usd >= 0.0
