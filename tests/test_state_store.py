from pathlib import Path

import pytest

from orchestration.persistence.state_store import ClaimStateStore
from orchestration.state import ClaimRecord, ClaimState


@pytest.fixture
def store(tmp_path: Path) -> ClaimStateStore:
    return ClaimStateStore(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# upsert + get_current
# ---------------------------------------------------------------------------

def test_get_current_returns_none_for_unknown_claim(store: ClaimStateStore) -> None:
    assert store.get_current("nonexistent-001") is None


def test_upsert_and_retrieve(store: ClaimStateStore) -> None:
    record = ClaimRecord(claim_id="c-001")
    store.upsert(record)
    retrieved = store.get_current("c-001")
    assert retrieved is not None
    assert retrieved.claim_id == "c-001"
    assert retrieved.state == ClaimState.RECEIVED


def test_get_current_returns_latest_after_transition(store: ClaimStateStore) -> None:
    record = ClaimRecord(claim_id="c-001")
    store.upsert(record)
    routing = record.transition(ClaimState.ROUTING)
    store.upsert(routing)
    retrieved = store.get_current("c-001")
    assert retrieved is not None
    assert retrieved.state == ClaimState.ROUTING


def test_full_state_machine_stored_as_latest(store: ClaimStateStore) -> None:
    record = ClaimRecord(claim_id="c-002")
    for state in [ClaimState.ROUTING, ClaimState.EVIDENCE_GATHERING, ClaimState.COMPLETE]:
        record = record.transition(state)
        store.upsert(record)
    current = store.get_current("c-002")
    assert current is not None
    assert current.state == ClaimState.COMPLETE


def test_upsert_persists_claim_type(store: ClaimStateStore) -> None:
    record = ClaimRecord(claim_id="c-003", claim_type="auto", routing_confidence=0.93)
    store.upsert(record)
    retrieved = store.get_current("c-003")
    assert retrieved is not None
    assert retrieved.claim_type == "auto"
    assert retrieved.routing_confidence == pytest.approx(0.93)


def test_upsert_persists_error_message(store: ClaimStateStore) -> None:
    record = ClaimRecord(claim_id="c-004")
    failed = record.transition(ClaimState.FAILED, error="VLM timeout")
    store.upsert(failed)
    retrieved = store.get_current("c-004")
    assert retrieved is not None
    assert retrieved.error_message == "VLM timeout"


# ---------------------------------------------------------------------------
# list_by_state
# ---------------------------------------------------------------------------

def test_list_by_state_returns_matching_claims(store: ClaimStateStore) -> None:
    for claim_id in ["c-010", "c-011", "c-012"]:
        r = ClaimRecord(claim_id=claim_id)
        store.upsert(r.transition(ClaimState.HUMAN_REVIEW))

    results = store.list_by_state(ClaimState.HUMAN_REVIEW)
    assert set(results) == {"c-010", "c-011", "c-012"}


def test_list_by_state_excludes_claims_in_different_state(store: ClaimStateStore) -> None:
    r = ClaimRecord(claim_id="c-020")
    store.upsert(r)  # RECEIVED
    store.upsert(r.transition(ClaimState.COMPLETE))

    assert "c-020" not in store.list_by_state(ClaimState.RECEIVED)
    assert "c-020" in store.list_by_state(ClaimState.COMPLETE)


def test_list_by_state_returns_empty_when_none_match(store: ClaimStateStore) -> None:
    assert store.list_by_state(ClaimState.FAILED) == []


# ---------------------------------------------------------------------------
# count_by_state
# ---------------------------------------------------------------------------

def test_count_by_state_reflects_current_states(store: ClaimStateStore) -> None:
    store.upsert(ClaimRecord(claim_id="c-030").transition(ClaimState.COMPLETE))
    store.upsert(ClaimRecord(claim_id="c-031").transition(ClaimState.COMPLETE))
    store.upsert(ClaimRecord(claim_id="c-032").transition(ClaimState.HUMAN_REVIEW))

    counts = store.count_by_state()
    assert counts.get("complete") == 2
    assert counts.get("human_review") == 1


def test_count_by_state_counts_current_not_historical(store: ClaimStateStore) -> None:
    record = ClaimRecord(claim_id="c-040")
    store.upsert(record)                              # RECEIVED
    store.upsert(record.transition(ClaimState.COMPLETE))  # COMPLETE

    counts = store.count_by_state()
    assert counts.get("received", 0) == 0
    assert counts.get("complete", 0) == 1


# ---------------------------------------------------------------------------
# Multiple independent claims
# ---------------------------------------------------------------------------

def test_independent_claims_do_not_interfere(store: ClaimStateStore) -> None:
    store.upsert(ClaimRecord(claim_id="x-001").transition(ClaimState.COMPLETE))
    store.upsert(ClaimRecord(claim_id="x-002").transition(ClaimState.FAILED))

    assert store.get_current("x-001").state == ClaimState.COMPLETE  # type: ignore[union-attr]
    assert store.get_current("x-002").state == ClaimState.FAILED    # type: ignore[union-attr]
