import pytest

from orchestration.state import (
    AgentStatus,
    ClaimRecord,
    ClaimState,
    ConsistencyFlag,
    CrossRef,
    DamageFinding,
    DocumentFinding,
    EvidenceStore,
    FraudSignal,
    PolicyFinding,
    StatementFinding,
)


# ---------------------------------------------------------------------------
# EvidenceStore — construction
# ---------------------------------------------------------------------------

def test_evidence_store_defaults_to_empty_lists() -> None:
    store = EvidenceStore(claim_id="c-001")
    assert store.damage_findings == []
    assert store.document_findings == []
    assert store.statement_findings == []
    assert store.policy_findings == []
    assert store.fraud_signals == []
    assert store.consistency_flags == []
    assert store.specialist_status == {}


def test_evidence_store_claim_id_preserved() -> None:
    store = EvidenceStore(claim_id="xyz-999")
    assert store.claim_id == "xyz-999"


# ---------------------------------------------------------------------------
# EvidenceStore.mark_agent — immutability
# ---------------------------------------------------------------------------

def test_mark_agent_returns_new_instance() -> None:
    store = EvidenceStore(claim_id="c-001")
    updated = store.mark_agent("damage_assessor", AgentStatus.SUCCESS)
    assert updated is not store


def test_mark_agent_does_not_mutate_original() -> None:
    store = EvidenceStore(claim_id="c-001")
    store.mark_agent("damage_assessor", AgentStatus.SUCCESS)
    assert "damage_assessor" not in store.specialist_status


def test_mark_agent_sets_status_correctly() -> None:
    store = EvidenceStore(claim_id="c-001")
    updated = store.mark_agent("damage_assessor", AgentStatus.SUCCESS)
    assert updated.specialist_status["damage_assessor"] == AgentStatus.SUCCESS


def test_mark_agent_overwrites_existing_status() -> None:
    store = EvidenceStore(claim_id="c-001")
    store = store.mark_agent("damage_assessor", AgentStatus.PARTIAL)
    store = store.mark_agent("damage_assessor", AgentStatus.SUCCESS)
    assert store.specialist_status["damage_assessor"] == AgentStatus.SUCCESS


def test_mark_agent_preserves_other_statuses() -> None:
    store = EvidenceStore(claim_id="c-001")
    store = store.mark_agent("damage_assessor", AgentStatus.SUCCESS)
    store = store.mark_agent("document_extractor", AgentStatus.FAILED)
    assert store.specialist_status["damage_assessor"] == AgentStatus.SUCCESS
    assert store.specialist_status["document_extractor"] == AgentStatus.FAILED


def test_mark_multiple_agents_accumulates() -> None:
    store = EvidenceStore(claim_id="c-001")
    for name, status in [
        ("damage_assessor", AgentStatus.SUCCESS),
        ("document_extractor", AgentStatus.PARTIAL),
        ("statement_analyst", AgentStatus.TIMEOUT),
    ]:
        store = store.mark_agent(name, status)
    assert len(store.specialist_status) == 3


# ---------------------------------------------------------------------------
# EvidenceStore.agent_succeeded
# ---------------------------------------------------------------------------

def test_agent_succeeded_true_when_success() -> None:
    store = EvidenceStore(claim_id="c-001").mark_agent("adjudicator", AgentStatus.SUCCESS)
    assert store.agent_succeeded("adjudicator")


def test_agent_succeeded_false_when_partial() -> None:
    store = EvidenceStore(claim_id="c-001").mark_agent("adjudicator", AgentStatus.PARTIAL)
    assert not store.agent_succeeded("adjudicator")


def test_agent_succeeded_false_when_absent() -> None:
    store = EvidenceStore(claim_id="c-001")
    assert not store.agent_succeeded("damage_assessor")


# ---------------------------------------------------------------------------
# EvidenceStore.all_agents_terminal
# ---------------------------------------------------------------------------

def test_all_agents_terminal_true_when_all_done() -> None:
    store = EvidenceStore(claim_id="c-001")
    for name, status in [
        ("damage_assessor", AgentStatus.SUCCESS),
        ("document_extractor", AgentStatus.FAILED),
        ("statement_analyst", AgentStatus.SKIPPED),
    ]:
        store = store.mark_agent(name, status)
    assert store.all_agents_terminal()


def test_all_agents_terminal_false_when_empty() -> None:
    store = EvidenceStore(claim_id="c-001")
    assert not store.all_agents_terminal()


# ---------------------------------------------------------------------------
# ClaimRecord.transition — immutability
# ---------------------------------------------------------------------------

def test_transition_returns_new_instance() -> None:
    record = ClaimRecord(claim_id="c-001")
    updated = record.transition(ClaimState.ROUTING)
    assert updated is not record


def test_transition_does_not_mutate_original() -> None:
    record = ClaimRecord(claim_id="c-001")
    record.transition(ClaimState.ROUTING)
    assert record.state == ClaimState.RECEIVED


def test_transition_sets_new_state() -> None:
    record = ClaimRecord(claim_id="c-001")
    updated = record.transition(ClaimState.EVIDENCE_GATHERING)
    assert updated.state == ClaimState.EVIDENCE_GATHERING


def test_transition_updates_timestamp() -> None:
    record = ClaimRecord(claim_id="c-001")
    updated = record.transition(ClaimState.ROUTING)
    assert updated.updated_at >= record.updated_at


def test_transition_preserves_created_at() -> None:
    record = ClaimRecord(claim_id="c-001")
    updated = record.transition(ClaimState.ROUTING)
    assert updated.created_at == record.created_at


def test_transition_sets_error_message() -> None:
    record = ClaimRecord(claim_id="c-001")
    updated = record.transition(ClaimState.FAILED, error="timeout on VLM")
    assert updated.error_message == "timeout on VLM"


def test_transition_clears_error_on_recovery() -> None:
    record = ClaimRecord(claim_id="c-001")
    failed = record.transition(ClaimState.FAILED, error="something broke")
    recovered = failed.transition(ClaimState.HUMAN_REVIEW, error=None)
    assert recovered.error_message is None


# ---------------------------------------------------------------------------
# Finding models — field validation
# ---------------------------------------------------------------------------

def test_damage_finding_confidence_bounds() -> None:
    with pytest.raises(Exception):
        DamageFinding(
            region_id="r1",
            category="cosmetic",
            description="scratch",
            estimated_cost_usd=100.0,
            cost_confidence=1.5,  # out of range
            evidence_uri="s3://bucket/r1.jpg",
        )


def test_document_finding_confidence_bounds() -> None:
    with pytest.raises(Exception):
        DocumentFinding(
            field_name="date",
            value="2026-01-01",
            page=1,
            bbox=(0.0, 0.0, 1.0, 1.0),
            extraction_confidence=-0.1,  # out of range
        )


def test_policy_finding_valid_corpus_layer() -> None:
    finding = PolicyFinding(
        clause_id="MASTER-HO3-4.3.2",
        corpus_layer="endorsement",
        determination="denied",
        cited_text="Flood damage is excluded.",
        confidence=0.92,
    )
    assert finding.corpus_layer == "endorsement"


def test_fraud_signal_severity_values() -> None:
    signal = FraudSignal(
        signal_type="velocity_anomaly",
        description="3 claims in 14 days",
        severity="high",
        confidence=0.87,
        source="tabular_model",
    )
    assert signal.severity == "high"


def test_consistency_flag_involved_findings_defaults_empty() -> None:
    flag = ConsistencyFlag(
        flag_type="date_mismatch",
        description="Photo EXIF predates incident date by 3 weeks.",
        severity="critical",
    )
    assert flag.involved_findings == []


def test_cross_ref_relationship_values() -> None:
    ref = CrossRef(
        target_finding_type="document",
        target_id="doc-field-001",
        relationship="contradicts",
        note="Statement says red car; report says blue.",
    )
    assert ref.relationship == "contradicts"
