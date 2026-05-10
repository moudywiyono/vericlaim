from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas import (
    HistoryItem,
    HistoryResponse,
    OfficerDecisionRequest,
    OfficerDecisionResponse,
    ReviewDetailResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from backend.services.claim_runner import load_result, save_result
from orchestration.persistence.state_store import ClaimStateStore
from orchestration.state import ClaimState

router = APIRouter(prefix="/review", tags=["review"])
_state_store = ClaimStateStore()


@router.get("/queue", response_model=ReviewQueueResponse)
async def get_review_queue() -> ReviewQueueResponse:
    claim_ids = _state_store.list_by_state(ClaimState.HUMAN_REVIEW)
    items: list[ReviewQueueItem] = []

    for claim_id in claim_ids:
        record = _state_store.get_current(claim_id)
        if record is None:
            continue
        result = load_result(claim_id)
        fraud_count = len(result.get("fraud_signals", [])) if result else 0
        items.append(ReviewQueueItem(
            claim_id=claim_id,
            state=record.state.value,
            claim_type=record.claim_type,
            routing_confidence=record.routing_confidence,
            fraud_signal_count=fraud_count,
            created_at=record.created_at.isoformat(),
        ))

    return ReviewQueueResponse(items=items, total=len(items))


@router.get("/history", response_model=HistoryResponse)
async def get_history() -> HistoryResponse:
    records = _state_store.list_by_states([
        ClaimState.APPROVED, ClaimState.DENIED, ClaimState.COMPLETE,
    ])
    items: list[HistoryItem] = []
    for record in sorted(records, key=lambda r: r.updated_at, reverse=True):
        result = load_result(record.claim_id)
        fraud_count = len(result.get("fraud_signals", [])) if result else 0
        officer_note = result.get("officer_note", "") if result else ""
        items.append(HistoryItem(
            claim_id=record.claim_id,
            state=record.state.value,
            claim_type=record.claim_type,
            routing_confidence=record.routing_confidence,
            fraud_signal_count=fraud_count,
            officer_note=officer_note,
            decided_at=record.updated_at.isoformat(),
        ))
    return HistoryResponse(items=items, total=len(items))


@router.get("/{claim_id}", response_model=ReviewDetailResponse)
async def get_review_detail(claim_id: str) -> ReviewDetailResponse:
    record = _state_store.get_current(claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Claim not found.")

    result = load_result(claim_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not available yet.")

    return ReviewDetailResponse(
        claim_id=claim_id,
        state=record.state.value,
        claim_type=record.claim_type,
        routing_confidence=record.routing_confidence,
        evidence=result,
    )


@router.patch("/{claim_id}/decision", response_model=OfficerDecisionResponse)
async def post_officer_decision(
    claim_id: str,
    body: OfficerDecisionRequest,
) -> OfficerDecisionResponse:
    record = _state_store.get_current(claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Claim not found.")

    decision_state = {
        "approve": ClaimState.APPROVED,
        "deny": ClaimState.DENIED,
        "request_info": ClaimState.HUMAN_REVIEW,
    }[body.decision]

    updated = record.transition(decision_state)
    _state_store.upsert(updated)

    if body.note and body.note.strip():
        result = load_result(claim_id)
        if result is not None:
            result["officer_note"] = body.note.strip()
            save_result(claim_id, result)

    return OfficerDecisionResponse(
        claim_id=claim_id,
        decision=body.decision,
        note=body.note,
    )
