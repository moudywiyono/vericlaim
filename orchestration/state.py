from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Claim state machine
# ---------------------------------------------------------------------------

class ClaimState(str, Enum):
    RECEIVED = "received"
    ROUTING = "routing"
    EVIDENCE_GATHERING = "evidence_gathering"
    REASONING = "reasoning"
    ADJUDICATING = "adjudicating"
    DRAFTING = "drafting"
    COMPLETE = "complete"
    APPROVED = "approved"
    DENIED = "denied"
    FAILED = "failed"
    HUMAN_REVIEW = "human_review"


class AgentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class ClaimRecord(BaseModel):
    """Persisted state-machine row for a single claim."""

    claim_id: str
    state: ClaimState = ClaimState.RECEIVED
    claim_type: str | None = None
    routing_confidence: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: str | None = None

    def transition(self, new_state: ClaimState, *, error: str | None = None) -> "ClaimRecord":
        return self.model_copy(
            update={
                "state": new_state,
                "updated_at": datetime.now(timezone.utc),
                "error_message": error,
            }
        )


# ---------------------------------------------------------------------------
# Finding types
# ---------------------------------------------------------------------------

class CrossRef(BaseModel):
    """A link from one finding to another for cross-modal consistency checks."""

    target_finding_type: str  # "document" | "image" | "statement" | "policy"
    target_id: str
    relationship: Literal["corroborates", "contradicts", "unclear"]
    note: str = ""


class DamageFinding(BaseModel):
    region_id: str
    category: Literal["cosmetic", "moderate", "severe", "total_loss"]
    description: str
    estimated_cost_usd: float
    cost_confidence: float = Field(ge=0.0, le=1.0)
    evidence_uri: str  # pointer to bbox-cropped image or asset


class DocumentFinding(BaseModel):
    field_name: str
    value: str
    page: int
    bbox: tuple[float, float, float, float]
    extraction_confidence: float = Field(ge=0.0, le=1.0)


class StatementFinding(BaseModel):
    claim: str
    timestamp_in_audio: float
    speaker_confidence: float = Field(ge=0.0, le=1.0)
    cross_refs: list[CrossRef] = Field(default_factory=list)


class PolicyFinding(BaseModel):
    clause_id: str
    corpus_layer: Literal["policy", "endorsement", "regulation", "guideline"]
    determination: Literal["covered", "denied", "partial", "ambiguous", "needs_review"]
    cited_text: str  # verbatim text extracted by Policy Reasoner — NOT the full document
    confidence: float = Field(ge=0.0, le=1.0)
    endorsements_applied: list[str] = Field(default_factory=list)


class FraudSignal(BaseModel):
    signal_type: str  # e.g. "staged_damage", "velocity_anomaly", "narrative_inconsistency"
    description: str
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["tabular_model", "llm_soft_signal", "rule"]


class ConsistencyFlag(BaseModel):
    flag_type: str  # e.g. "date_mismatch", "damage_narrative_conflict"
    description: str
    severity: Literal["minor", "major", "critical"]
    involved_findings: list[str] = Field(default_factory=list)  # finding IDs


# ---------------------------------------------------------------------------
# EvidenceStore — the typed boundary between specialist and reasoning layers
# ---------------------------------------------------------------------------

class EvidenceStore(BaseModel):
    claim_id: str
    damage_findings: list[DamageFinding] = Field(default_factory=list)
    document_findings: list[DocumentFinding] = Field(default_factory=list)
    statement_findings: list[StatementFinding] = Field(default_factory=list)
    policy_findings: list[PolicyFinding] = Field(default_factory=list)
    fraud_signals: list[FraudSignal] = Field(default_factory=list)
    consistency_flags: list[ConsistencyFlag] = Field(default_factory=list)
    specialist_status: dict[str, AgentStatus] = Field(default_factory=dict)
    claimant_letter: str = ""
    officer_note: str = ""

    def mark_agent(self, agent_name: str, status: AgentStatus) -> "EvidenceStore":
        updated = dict(self.specialist_status)
        updated[agent_name] = status
        return self.model_copy(update={"specialist_status": updated})

    def agent_succeeded(self, agent_name: str) -> bool:
        return self.specialist_status.get(agent_name) == AgentStatus.SUCCESS

    def all_agents_terminal(self) -> bool:
        if not self.specialist_status:
            return False
        terminal = {AgentStatus.SUCCESS, AgentStatus.PARTIAL, AgentStatus.FAILED,
                    AgentStatus.TIMEOUT, AgentStatus.SKIPPED}
        return all(s in terminal for s in self.specialist_status.values())
