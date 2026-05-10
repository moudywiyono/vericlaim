from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


# --- Claim submission ---

class ClaimSubmitResponse(BaseModel):
    claim_id: str
    status: str = "processing"


# --- Status polling ---

class ClaimStatusResponse(BaseModel):
    claim_id: str
    state: str
    claim_type: str | None
    routing_confidence: float | None
    specialist_status: dict[str, str]
    is_terminal: bool


# --- Full result ---

class ClaimResultResponse(BaseModel):
    claim_id: str
    state: str
    evidence: dict[str, Any]


# --- Review queue ---

class ReviewQueueItem(BaseModel):
    claim_id: str
    state: str
    claim_type: str | None
    routing_confidence: float | None
    fraud_signal_count: int
    created_at: str


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    total: int


# --- Review detail ---

class ReviewDetailResponse(BaseModel):
    claim_id: str
    state: str
    claim_type: str | None
    routing_confidence: float | None
    evidence: dict[str, Any]


# --- History ---

class HistoryItem(BaseModel):
    claim_id: str
    state: str
    claim_type: str | None
    routing_confidence: float | None
    fraud_signal_count: int
    officer_note: str
    decided_at: str


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    total: int


# --- Officer decision ---

class OfficerDecisionRequest(BaseModel):
    decision: Literal["approve", "deny", "request_info"]
    note: str = ""


class OfficerDecisionResponse(BaseModel):
    claim_id: str
    decision: str
    note: str
