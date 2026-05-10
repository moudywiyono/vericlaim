from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from backend.config import settings
from backend.schemas import ClaimResultResponse, ClaimStatusResponse, ClaimSubmitResponse
from backend.services.claim_runner import (
    generate_claim_id,
    is_terminal,
    load_result,
    run_pipeline_background,
    save_uploaded_files,
)
from orchestration.persistence.state_store import ClaimStateStore

router = APIRouter(prefix="/claims", tags=["claims"])
_state_store = ClaimStateStore()


@router.post("", response_model=ClaimSubmitResponse, status_code=202)
async def submit_claim(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(default=[]),
    description: str = Form(default=""),
    claim_type: str | None = Form(default=None),
) -> ClaimSubmitResponse:
    if not files and not description:
        raise HTTPException(status_code=422, detail="Provide at least one file or a description.")

    claim_id = generate_claim_id()
    claim_dir = await save_uploaded_files(claim_id, files, description, claim_type)
    background_tasks.add_task(
        asyncio.run,
        run_pipeline_background(claim_id, claim_dir),
    )
    return ClaimSubmitResponse(claim_id=claim_id)


@router.get("/{claim_id}/status", response_model=ClaimStatusResponse)
async def get_claim_status(claim_id: str) -> ClaimStatusResponse:
    record = _state_store.get_current(claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Claim not found.")

    result = load_result(claim_id)
    specialist_status: dict[str, str] = {}
    if result:
        specialist_status = {
            k: v for k, v in result.get("specialist_status", {}).items()
        }

    return ClaimStatusResponse(
        claim_id=claim_id,
        state=record.state.value,
        claim_type=record.claim_type,
        routing_confidence=record.routing_confidence,
        specialist_status=specialist_status,
        is_terminal=is_terminal(record.state.value),
    )


@router.get("/{claim_id}/result", response_model=ClaimResultResponse)
async def get_claim_result(claim_id: str) -> ClaimResultResponse:
    record = _state_store.get_current(claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if not is_terminal(record.state.value):
        raise HTTPException(status_code=202, detail="Pipeline still running.")

    result = load_result(claim_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not yet available.")

    return ClaimResultResponse(
        claim_id=claim_id,
        state=record.state.value,
        evidence=result,
    )


@router.get("/{claim_id}/files")
async def list_claim_files(claim_id: str) -> dict:
    claim_dir = settings.upload_dir / claim_id
    if not claim_dir.exists():
        raise HTTPException(status_code=404, detail="Claim not found.")
    manifest_path = claim_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not available.")
    manifest = json.loads(manifest_path.read_text())
    return {
        "images": manifest.get("images", []),
        "pdfs": manifest.get("pdfs", []),
        "audio": manifest.get("audio", []),
        "description": manifest.get("form_data", {}).get("description", ""),
    }


@router.get("/{claim_id}/files/{filename}")
async def get_claim_file(claim_id: str, filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    file_path = settings.upload_dir / claim_id / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(str(file_path), media_type=mime_type or "application/octet-stream")
