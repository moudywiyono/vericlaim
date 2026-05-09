"""
Statement Analyst node.

Pipeline:
  1. (Optional) Whisper ASR to transcribe audio files — degrades gracefully if
     whisper is not installed
  2. If no audio / transcription unavailable, uses claim description from form_data
  3. LLM analysis extracts StatementFinding objects per factual claim

Status: SUCCESS (findings extracted from transcripts or description),
        PARTIAL (some audio failed, or Whisper unavailable for some files),
        FAILED (all transcript analyses failed),
        SKIPPED (no audio and no description).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

import litellm
from pydantic import BaseModel, Field, ValidationError, field_validator

from ingestion.models import ClaimPacket
from orchestration.nodes.base import Node, NodeResult
from orchestration.state import AgentStatus, CrossRef, EvidenceStore, StatementFinding

logger = logging.getLogger(__name__)

_MODEL = os.getenv("VERICLAIM_DEFAULT_MODEL", "claude-sonnet-4-6")
_MAX_PARSE_RETRIES = 2

_ANALYSIS_PROMPT = """\
{degraded_notice}\
Analyze this insurance claimant statement and extract key factual claims.

TRANSCRIPT:
{transcript}

CLAIM CONTEXT:
{claim_context}

For each factual claim relevant to the insurance loss, provide:
- claim: the specific assertion made (concise, one sentence)
- timestamp_in_audio: seconds into the audio (use 0.0 if not from audio)
- speaker_confidence: your confidence the speaker made this claim clearly (0.0–1.0)
- cross_refs: references to other evidence (leave empty if none)

Respond with valid JSON only, no markdown fences:
{{
  "findings": [
    {{
      "claim": "...",
      "timestamp_in_audio": 0.0,
      "speaker_confidence": 0.8,
      "cross_refs": []
    }}
  ]
}}"""


class _CrossRefRaw(BaseModel):
    target_finding_type: str
    target_id: str
    relationship: Literal["corroborates", "contradicts", "unclear"]
    note: str = ""


class _StatementFindingRaw(BaseModel):
    claim: str
    timestamp_in_audio: float = 0.0
    speaker_confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    cross_refs: list[_CrossRefRaw] = Field(default_factory=list)

    @field_validator("cross_refs", mode="before")
    @classmethod
    def drop_non_dict_refs(cls, v: list) -> list:
        return [item for item in v if isinstance(item, dict)]


class _StatementAnalysisResponse(BaseModel):
    findings: list[_StatementFindingRaw]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    return text.strip()


def _try_whisper_transcribe(audio_path: Path) -> str | None:
    try:
        import whisper  # type: ignore[import-untyped]

        model = whisper.load_model("base")
        result = model.transcribe(str(audio_path))
        return (result.get("text") or "").strip() or None
    except ImportError:
        logger.warning("whisper not installed; cannot transcribe %s", audio_path.name)
        return None
    except Exception as e:
        logger.error("Whisper transcription failed for %s: %s", audio_path.name, e)
        return None


async def _analyze_transcript(
    transcript: str,
    claim_context: str,
    degraded_context: dict[str, str] | None,
) -> tuple[list[StatementFinding], float]:
    degraded_notice = ""
    if degraded_context:
        lines = "\n".join(f"- {v}" for v in degraded_context.values())
        degraded_notice = f"Context notes:\n{lines}\n\n"

    prompt = _ANALYSIS_PROMPT.format(
        degraded_notice=degraded_notice,
        transcript=transcript[:6000],
        claim_context=claim_context,
    )

    parse_error: str | None = None
    cost_usd = 0.0
    analyzed: _StatementAnalysisResponse | None = None

    for attempt in range(_MAX_PARSE_RETRIES + 1):
        full_prompt = (
            prompt
            if not parse_error
            else f"{prompt}\n\nPrevious parse error — return valid JSON: {parse_error}"
        )
        response = await litellm.acompletion(
            model=_MODEL,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.0,
        )
        try:
            cost_usd += litellm.completion_cost(completion_response=response)
        except Exception:
            pass

        raw = response.choices[0].message.content or ""
        try:
            analyzed = _StatementAnalysisResponse.model_validate(
                json.loads(_strip_fences(raw))
            )
            break
        except (json.JSONDecodeError, ValidationError) as e:
            if attempt < _MAX_PARSE_RETRIES:
                parse_error = str(e)
                logger.warning(
                    "Statement analysis parse error (attempt %d): %s", attempt + 1, e
                )
            else:
                raise

    assert analyzed is not None
    findings = [
        StatementFinding(
            claim=f.claim,
            timestamp_in_audio=f.timestamp_in_audio,
            speaker_confidence=f.speaker_confidence,
            cross_refs=[
                CrossRef(
                    target_finding_type=cr.target_finding_type,
                    target_id=cr.target_id,
                    relationship=cr.relationship,
                    note=cr.note,
                )
                for cr in f.cross_refs
            ],
        )
        for f in analyzed.findings
    ]
    return findings, cost_usd


class StatementAnalystNode(Node):
    """
    Transcribes audio (Whisper, optional) and extracts StatementFindings via LLM.

    Falls back to analyzing the claim description from form_data when no audio
    is present or Whisper is unavailable.
    """

    @property
    def name(self) -> str:
        return "statement_analyst"

    @property
    def timeout_s(self) -> float:
        return 120.0

    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        claim_context = (
            str(packet.form_data.get("description", "")).strip()
            or f"Claim {store.claim_id}"
        )

        transcripts: list[str] = []
        whisper_failed = 0

        for audio_path in packet.audio:
            transcript = _try_whisper_transcribe(audio_path)
            if transcript:
                transcripts.append(transcript)
            else:
                whisper_failed += 1

        # Fall back to claim description if no transcripts
        if not transcripts:
            description = str(packet.form_data.get("description", "")).strip()
            if description:
                transcripts.append(description)
            else:
                return self._skipped_result(store)

        all_findings: list[StatementFinding] = []
        total_cost = 0.0
        failed_count = 0

        for transcript in transcripts:
            try:
                findings, cost = await _analyze_transcript(
                    transcript, claim_context, degraded_context
                )
                all_findings.extend(findings)
                total_cost += cost
            except Exception as e:
                logger.error("Statement analysis failed: %s", e)
                failed_count += 1

        if failed_count == len(transcripts):
            status = AgentStatus.FAILED
        elif failed_count > 0 or whisper_failed > 0 or not all_findings:
            status = AgentStatus.PARTIAL
        else:
            status = AgentStatus.SUCCESS

        return NodeResult(
            store=self._delta(store, status, statement_findings=all_findings),
            status=status,
            cost_usd=total_cost,
        )
