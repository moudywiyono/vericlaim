"""
Zero-shot claim type classifier.

Primary: HuggingFace zero-shot pipeline (facebook/bart-large-mnli), runs locally.
Fallback: LiteLLM call when HF pipeline is unavailable or confidence is too low.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from ingestion.models import ClaimPacket, ClaimType, RoutingDecision

logger = logging.getLogger(__name__)

_CANDIDATE_LABELS = [
    "auto insurance claim",
    "property insurance claim",
    "liability insurance claim",
    "health insurance claim",
]

_LABEL_TO_CLAIM_TYPE: dict[str, ClaimType] = {
    "auto insurance claim": ClaimType.AUTO,
    "property insurance claim": ClaimType.PROPERTY,
    "liability insurance claim": ClaimType.LIABILITY,
    "health insurance claim": ClaimType.HEALTH,
}

_CONFIDENCE_THRESHOLD = float(os.getenv("VERICLAIM_ROUTER_CONFIDENCE_THRESHOLD", "0.5"))
_HF_MODEL = os.getenv("HF_ZERO_SHOT_MODEL", "facebook/bart-large-mnli")
_FALLBACK_MODEL = os.getenv("VERICLAIM_ROUTER_FALLBACK_MODEL", "claude-haiku-4-5-20251001")


def _build_routing_text(packet: ClaimPacket) -> str:
    """Produce a short text summary of the claim suitable for classification."""
    parts: list[str] = []
    if desc := packet.form_data.get("description"):
        parts.append(str(desc))
    if incident_type := packet.form_data.get("incident_type"):
        parts.append(str(incident_type))
    if not parts:
        parts.append(f"Insurance claim with {len(packet.images)} images, "
                     f"{len(packet.pdfs)} documents, {len(packet.audio)} audio files.")
    return " ".join(parts)


class ClaimRouter:
    """
    Routes a ClaimPacket to a ClaimType.

    Tries HF zero-shot classification first; falls back to LiteLLM if the pipeline
    fails or returns confidence below the configured threshold.
    """

    def __init__(self) -> None:
        self._hf_pipeline: Any = None
        self._hf_loaded = False

    def _load_hf_pipeline(self) -> bool:
        if self._hf_loaded:
            return self._hf_pipeline is not None
        self._hf_loaded = True
        try:
            from transformers import pipeline  # type: ignore[import-untyped]

            self._hf_pipeline = pipeline(
                "zero-shot-classification",
                model=_HF_MODEL,
                device=-1,  # CPU; override with device=0 for GPU
            )
            logger.info("HF zero-shot pipeline loaded: %s", _HF_MODEL)
            return True
        except Exception as e:
            logger.warning("Failed to load HF pipeline (%s), will use LLM fallback: %s", _HF_MODEL, e)
            return False

    def _route_via_hf(self, text: str) -> RoutingDecision | None:
        if not self._load_hf_pipeline():
            return None
        try:
            result = self._hf_pipeline(text, candidate_labels=_CANDIDATE_LABELS)
            top_label: str = result["labels"][0]
            top_score: float = result["scores"][0]

            if top_score < _CONFIDENCE_THRESHOLD:
                logger.debug(
                    "HF confidence %.2f below threshold %.2f for label '%s'; falling back.",
                    top_score, _CONFIDENCE_THRESHOLD, top_label,
                )
                return None

            return RoutingDecision(
                claim_type=_LABEL_TO_CLAIM_TYPE[top_label],
                confidence=top_score,
                source="hf",
            )
        except Exception as e:
            logger.warning("HF pipeline inference failed: %s", e)
            return None

    def _route_via_llm(self, text: str) -> RoutingDecision:
        import litellm  # type: ignore[import-untyped]

        prompt = (
            "Classify this insurance claim into exactly one category: "
            "auto, property, liability, or health.\n\n"
            f"Claim description: {text}\n\n"
            'Respond with JSON only: {"claim_type": "<type>", "confidence": <0.0-1.0>, "reasoning": "<brief>"}'
        )
        response = litellm.completion(
            model=_FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        claim_type_str: str = parsed["claim_type"].lower().strip()
        try:
            claim_type = ClaimType(claim_type_str)
        except ValueError:
            claim_type = ClaimType.UNKNOWN
        return RoutingDecision(
            claim_type=claim_type,
            confidence=float(parsed.get("confidence", 0.5)),
            source="llm",
        )

    def route(self, packet: ClaimPacket) -> RoutingDecision:
        """
        Classify a claim packet. Returns RoutingDecision with source indicating
        whether the HF pipeline or LLM fallback was used.
        """
        # Honour an explicit type set during ingestion (e.g. from a trusted intake form)
        if packet.claim_type is not None:
            return RoutingDecision(
                claim_type=packet.claim_type,
                confidence=1.0,
                source="form_data",
            )

        text = _build_routing_text(packet)

        decision = self._route_via_hf(text)
        if decision is not None:
            return decision

        return self._route_via_llm(text)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from dotenv import load_dotenv

    from ingestion.intake import load_claim_from_manifest

    load_dotenv()

    parser = argparse.ArgumentParser(description="Route a claim to its type.")
    parser.add_argument("--manifest-dir", type=Path, help="Path to claim directory.")
    parser.add_argument("--description", type=str, help="Ad-hoc description string to classify.")
    args = parser.parse_args()

    router = ClaimRouter()

    if args.manifest_dir:
        packet = load_claim_from_manifest(args.manifest_dir)
    else:
        desc = args.description or "The car was rear-ended at an intersection."
        packet = ClaimPacket(
            claim_id="cli-test",
            claim_dir=Path("."),
            form_data={"description": desc},
        )

    decision = router.route(packet)
    print(f"ClaimType: {decision.claim_type.value} | confidence={decision.confidence:.3f} | source={decision.source}")
