"""
Document Extractor node.

Pipeline:
  1. pypdf text extraction per page (fast path for digital PDFs)
  2. LiteLLM structured parsing — extracts named insurance fields with confidence scores
  Pages with sparse text (< _MIN_TEXT_CHARS chars) are marked as PARTIAL; VLM fallback
  for scanned PDFs is a Phase 3 enhancement.

Returns DocumentFinding per extracted field.
Status: SUCCESS (fields extracted), PARTIAL (some pages failed or sparse),
        FAILED (all PDFs failed), SKIPPED (no PDFs in claim).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

import litellm
from pydantic import BaseModel, Field, ValidationError

from ingestion.models import ClaimPacket
from orchestration.nodes.base import Node, NodeResult
from orchestration.state import AgentStatus, DocumentFinding, EvidenceStore

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_MAX_PARSE_RETRIES = 2
_MIN_TEXT_CHARS = 100  # pages below this are considered sparse (likely scanned)

_USER_PROMPT_TEMPLATE = """\
{degraded_notice}Extract all insurance claim fields from this document text (page {page}).

Document text:
{text}

Extract any of these fields if present:
date_of_loss, report_date, claimant_name, claimant_address, claimant_phone,
policy_number, policy_type, coverage_type,
vehicle_make, vehicle_model, vehicle_year, vehicle_vin, vehicle_plate,
incident_location, incident_description,
estimated_repair_cost, deductible_amount, prior_damage,
officer_name, officer_report_number, witness_names

For each field found provide:
- field_name: standardized name from the list above
- value: extracted value as a string
- confidence: 0.0–1.0

Also identify the document_type as one of: claim_form, police_report, \
repair_estimate, medical_bill, other.

Respond with valid JSON only, no markdown fences:
{{
  "document_type": "...",
  "fields": [
    {{
      "field_name": "...",
      "value": "...",
      "confidence": 0.0
    }}
  ],
  "note": ""
}}"""


class _FieldExtraction(BaseModel):
    field_name: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)


class _DocumentExtractionResponse(BaseModel):
    document_type: Literal[
        "claim_form", "police_report", "repair_estimate", "medical_bill", "other"
    ]
    fields: list[_FieldExtraction]
    note: str = ""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


async def _extract_page(
    text: str,
    page: int,
    degraded_context: dict[str, str] | None,
) -> tuple[list[DocumentFinding], float]:
    """Extract fields from one page of text. Returns (findings, cost_usd)."""
    degraded_notice = ""
    if degraded_context:
        lines = "\n".join(f"- {v}" for v in degraded_context.values())
        degraded_notice = f"Context notes:\n{lines}\n\n"

    base_prompt = _USER_PROMPT_TEMPLATE.format(
        degraded_notice=degraded_notice,
        page=page,
        text=text[:8000],  # cap to avoid token overflow on dense documents
    )

    parse_error: str | None = None
    cost_usd = 0.0
    extracted: _DocumentExtractionResponse | None = None

    for attempt in range(_MAX_PARSE_RETRIES + 1):
        prompt = (
            base_prompt if not parse_error
            else f"{base_prompt}\n\nPrevious response had a parse error — return valid JSON only: {parse_error}"
        )
        response = await litellm.acompletion(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        try:
            cost_usd += litellm.completion_cost(completion_response=response)
        except Exception:
            pass

        raw = response.choices[0].message.content or ""
        try:
            extracted = _DocumentExtractionResponse.model_validate(
                json.loads(_strip_fences(raw))
            )
            break
        except (json.JSONDecodeError, ValidationError) as e:
            if attempt < _MAX_PARSE_RETRIES:
                parse_error = str(e)
                logger.warning("Parse error page %d (attempt %d): %s", page, attempt + 1, e)
            else:
                raise

    assert extracted is not None
    full_page_bbox = (0.0, 0.0, 1.0, 1.0)  # page-level placeholder; precise bbox is Phase 3
    findings = [
        DocumentFinding(
            field_name=f.field_name,
            value=f.value,
            page=page,
            bbox=full_page_bbox,
            extraction_confidence=f.confidence,
        )
        for f in extracted.fields
    ]
    return findings, cost_usd


class DocumentExtractorNode(Node):
    """
    Extracts structured fields from insurance PDFs.

    Uses pypdf for text extraction, then LiteLLM for structured field parsing.
    Pages with sparse text (likely scanned) are skipped and counted as partial.
    VLM fallback for scanned pages is a Phase 3 enhancement.
    """

    @property
    def name(self) -> str:
        return "document_extractor"

    @property
    def timeout_s(self) -> float:
        return 60.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        if not packet.has_pdfs:
            return self._skipped_result(store)

        import pypdf

        all_findings: list[DocumentFinding] = []
        total_cost = 0.0
        failed_count = 0
        sparse_count = 0

        for pdf_path in packet.pdfs:
            try:
                reader = pypdf.PdfReader(str(pdf_path))
                for page_num, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if len(text.strip()) < _MIN_TEXT_CHARS:
                        logger.warning(
                            "Page %d of %s: sparse text (%d chars), skipping",
                            page_num, pdf_path.name, len(text.strip()),
                        )
                        sparse_count += 1
                        continue
                    findings, cost = await _extract_page(text, page_num, degraded_context)
                    all_findings.extend(findings)
                    total_cost += cost
            except Exception as e:
                logger.error("Failed to process %s: %s", pdf_path.name, e)
                failed_count += 1

        if failed_count == len(packet.pdfs):
            status = AgentStatus.FAILED
        elif failed_count > 0 or sparse_count > 0 or not all_findings:
            status = AgentStatus.PARTIAL
        else:
            status = AgentStatus.SUCCESS

        return NodeResult(
            store=self._delta(store, status, document_findings=all_findings),
            status=status,
            cost_usd=total_cost,
        )
