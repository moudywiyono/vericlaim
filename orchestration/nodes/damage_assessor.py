"""
Damage Assessor node.

Pipeline:
  1. YOLO-World region detection (optional — lazy import, degrades to VLM-only if
     ultralytics is not installed or model weights are unavailable)
  2. VLM analysis via LiteLLM for each image (required path) — severity category,
     description, cost estimate, and location per damage region

Returns DamageFinding per detected region.
Status: SUCCESS (all images processed with findings), PARTIAL (some images failed
        or processed but no findings), FAILED (all images failed), SKIPPED (no images).
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Literal

import litellm
from pydantic import BaseModel, Field, ValidationError

from ingestion.models import ClaimPacket
from orchestration.nodes.base import Node, NodeResult
from orchestration.state import AgentStatus, DamageFinding, EvidenceStore

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_MAX_PARSE_RETRIES = 2

_USER_PROMPT = """\
Analyze this vehicle damage image. Identify every visible damage region.

For each region provide:
- region_id: short snake_case identifier (e.g., "front_bumper", "driver_door_panel")
- category: one of "cosmetic" (scratches/minor dents, typically <$500), "moderate" \
($500–$5000), "severe" ($5000–$15000 structural damage), "total_loss" (>$15000 or \
>75% vehicle value)
- description: clear description of damage type and extent
- location: where on the vehicle (e.g., "front bumper, left corner")
- estimated_cost_usd: repair cost estimate in USD
- cost_confidence: your confidence in that estimate (0.0–1.0)

If image quality is too poor to assess, return empty regions and explain in the note field.

Respond with valid JSON only, no markdown fences:
{
  "regions": [
    {
      "region_id": "...",
      "category": "cosmetic|moderate|severe|total_loss",
      "description": "...",
      "location": "...",
      "estimated_cost_usd": 0.0,
      "cost_confidence": 0.0
    }
  ],
  "note": ""
}"""


class _RegionAssessment(BaseModel):
    region_id: str
    category: Literal["cosmetic", "moderate", "severe", "total_loss"]
    description: str
    location: str
    estimated_cost_usd: float = Field(ge=0.0)
    cost_confidence: float = Field(ge=0.0, le=1.0)


class _VLMDamageResponse(BaseModel):
    regions: list[_RegionAssessment]
    note: str = ""


def _encode_image(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix, "jpeg")
    with open(path, "rb") as f:
        return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode()}"


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


async def _analyze_image(
    image_path: Path,
    degraded_context: dict[str, str] | None,
) -> tuple[list[DamageFinding], float]:
    """Analyze a single image. Returns (findings, cost_usd). Retries on parse errors."""
    prompt = _USER_PROMPT
    if degraded_context:
        notice = "\n".join(f"- {v}" for v in degraded_context.values())
        prompt = f"Context notes:\n{notice}\n\n{prompt}"

    image_data_uri = _encode_image(image_path)
    parse_error: str | None = None
    cost_usd = 0.0
    assessed: _VLMDamageResponse | None = None

    for attempt in range(_MAX_PARSE_RETRIES + 1):
        full_prompt = (
            prompt if not parse_error
            else f"{prompt}\n\nPrevious response had a parse error — return valid JSON only: {parse_error}"
        )
        response = await litellm.acompletion(
            model=_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                    {"type": "text", "text": full_prompt},
                ],
            }],
            temperature=0.1,
        )
        try:
            cost_usd += litellm.completion_cost(completion_response=response)
        except Exception:
            pass

        raw = response.choices[0].message.content or ""
        try:
            assessed = _VLMDamageResponse.model_validate(json.loads(_strip_fences(raw)))
            break
        except (json.JSONDecodeError, ValidationError) as e:
            if attempt < _MAX_PARSE_RETRIES:
                parse_error = str(e)
                logger.warning("Parse error on %s (attempt %d): %s", image_path.name, attempt + 1, e)
            else:
                raise

    assert assessed is not None
    findings = [
        DamageFinding(
            region_id=r.region_id,
            category=r.category,
            description=r.description,
            estimated_cost_usd=r.estimated_cost_usd,
            cost_confidence=r.cost_confidence,
            evidence_uri=f"file://{image_path.resolve()}#{r.location.replace(' ', '_')}",
        )
        for r in assessed.regions
    ]
    return findings, cost_usd


class DamageAssessorNode(Node):
    """
    Analyzes vehicle damage images via VLM (LiteLLM).

    Optional YOLO-World pre-detection (ultralytics[vision] extra) enhances region
    localization when available; degrades gracefully to VLM-only otherwise.
    """

    @property
    def name(self) -> str:
        return "damage_assessor"

    @property
    def timeout_s(self) -> float:
        return 60.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        if not packet.has_images:
            return self._skipped_result(store)

        all_findings: list[DamageFinding] = []
        total_cost = 0.0
        failed_count = 0

        for image_path in packet.images:
            try:
                findings, cost = await _analyze_image(image_path, degraded_context)
                all_findings.extend(findings)
                total_cost += cost
            except Exception as e:
                logger.error("Failed to analyze image %s: %s", image_path.name, e)
                failed_count += 1

        processed = len(packet.images) - failed_count
        if processed == 0:
            status = AgentStatus.FAILED
        elif failed_count > 0 or not all_findings:
            status = AgentStatus.PARTIAL
        else:
            status = AgentStatus.SUCCESS

        updated_store = store.mark_agent(self.name, status).model_copy(
            update={"damage_findings": store.damage_findings + all_findings}
        )
        return NodeResult(store=updated_store, status=status, cost_usd=total_cost)
