"""
Wraps run_claim() for the API layer.

Responsibilities:
- Generate a claim_id and create an upload directory
- Write uploaded files + manifest.json into that directory
- Run the pipeline as a background task
- Persist the final EvidenceStore to result.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import UploadFile

from backend.config import settings

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {"complete", "approved", "denied", "human_review", "failed"}


def generate_claim_id() -> str:
    return "CLM-" + uuid.uuid4().hex[:8].upper()


async def save_uploaded_files(
    claim_id: str,
    files: list[UploadFile],
    description: str,
    claim_type: str | None,
) -> Path:
    claim_dir = settings.upload_dir / claim_id
    claim_dir.mkdir(parents=True, exist_ok=True)

    images, pdfs, audio = [], [], []

    for upload in files:
        filename = upload.filename or "file"
        dest = claim_dir / filename
        content = await upload.read()
        dest.write_bytes(content)

        suffix = Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            images.append(filename)
        elif suffix == ".pdf":
            pdfs.append(filename)
        elif suffix in {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".webm"}:
            audio.append(filename)

    manifest = {
        "claim_id": claim_id,
        "form_data": {"description": description},
        "images": images,
        "pdfs": pdfs,
        "audio": audio,
    }
    if claim_type:
        manifest["claim_type"] = claim_type

    (claim_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return claim_dir


async def run_pipeline_background(claim_id: str, claim_dir: Path) -> None:
    from dotenv import load_dotenv
    load_dotenv(".env")

    from orchestration.orchestrator import run_claim

    try:
        logger.info("Pipeline starting for %s", claim_id)
        result = await run_claim(claim_dir)
        result_path = claim_dir / "result.json"
        result_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2))
        logger.info("Pipeline complete for %s", claim_id)
    except Exception as e:
        logger.error("Pipeline failed for %s: %s", claim_id, e)


def load_result(claim_id: str) -> dict | None:
    result_path = settings.upload_dir / claim_id / "result.json"
    if not result_path.exists():
        return None
    return json.loads(result_path.read_text())


def save_result(claim_id: str, data: dict) -> None:
    result_path = settings.upload_dir / claim_id / "result.json"
    result_path.write_text(json.dumps(data, indent=2))


def is_terminal(state: str) -> bool:
    return state.lower() in _TERMINAL_STATES
