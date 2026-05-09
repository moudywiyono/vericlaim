from pathlib import Path

import pytest

from orchestration.persistence.trace_store import TraceStore


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    return TraceStore(trace_dir=tmp_path / "traces")


# ---------------------------------------------------------------------------
# record_node
# ---------------------------------------------------------------------------

def test_record_node_creates_trace_file(store: TraceStore, tmp_path: Path) -> None:
    store.record_node(
        claim_id="c-001",
        node_name="damage_assessor",
        attempt=1,
        status="success",
        elapsed_ms=1234,
        cost_usd=0.002,
    )
    trace_file = tmp_path / "traces" / "c-001.jsonl"
    assert trace_file.exists()


def test_record_node_appends_correct_fields(store: TraceStore) -> None:
    store.record_node(
        claim_id="c-001",
        node_name="document_extractor",
        attempt=1,
        status="success",
        elapsed_ms=500,
        cost_usd=0.001,
    )
    events = store.read_trace("c-001")
    assert len(events) == 1
    e = events[0]
    assert e["event"] == "node_execution"
    assert e["node_name"] == "document_extractor"
    assert e["status"] == "success"
    assert e["elapsed_ms"] == 500
    assert e["cost_usd"] == pytest.approx(0.001)
    assert e["attempt"] == 1


def test_record_node_includes_failure_type_when_provided(store: TraceStore) -> None:
    store.record_node(
        claim_id="c-002",
        node_name="adjudicator",
        attempt=2,
        status="failed",
        elapsed_ms=100,
        cost_usd=0.0,
        failure_type="transient",
        error="connection timeout",
    )
    events = store.read_trace("c-002")
    assert events[0]["failure_type"] == "transient"
    assert events[0]["error"] == "connection timeout"


def test_record_node_excludes_failure_type_when_absent(store: TraceStore) -> None:
    store.record_node(
        claim_id="c-003",
        node_name="router",
        attempt=1,
        status="success",
        elapsed_ms=50,
        cost_usd=0.0,
    )
    events = store.read_trace("c-003")
    assert "failure_type" not in events[0]
    assert "error" not in events[0]


def test_record_node_includes_metadata(store: TraceStore) -> None:
    store.record_node(
        claim_id="c-004",
        node_name="policy_reasoner",
        attempt=1,
        status="success",
        elapsed_ms=3000,
        cost_usd=0.01,
        metadata={"recall_at_5": 0.88, "reranker_top_score": 0.91},
    )
    events = store.read_trace("c-004")
    assert events[0]["metadata"]["recall_at_5"] == pytest.approx(0.88)


# ---------------------------------------------------------------------------
# record_claim (state transitions)
# ---------------------------------------------------------------------------

def test_record_claim_appends_state_event(store: TraceStore) -> None:
    store.record_claim(claim_id="c-010", state="routing", claim_type="auto")
    events = store.read_trace("c-010")
    assert len(events) == 1
    assert events[0]["event"] == "claim_state_transition"
    assert events[0]["state"] == "routing"
    assert events[0]["claim_type"] == "auto"


# ---------------------------------------------------------------------------
# Append-only behaviour
# ---------------------------------------------------------------------------

def test_multiple_records_append_in_order(store: TraceStore) -> None:
    for i, node in enumerate(["router", "damage_assessor", "adjudicator"]):
        store.record_node(
            claim_id="c-020",
            node_name=node,
            attempt=1,
            status="success",
            elapsed_ms=i * 100,
            cost_usd=0.0,
        )
    events = store.read_trace("c-020")
    assert len(events) == 3
    assert [e["node_name"] for e in events] == ["router", "damage_assessor", "adjudicator"]


def test_traces_isolated_per_claim(store: TraceStore) -> None:
    store.record_node("c-030", "router", 1, "success", 10, 0.0)
    store.record_node("c-031", "router", 1, "failed", 10, 0.0)

    assert len(store.read_trace("c-030")) == 1
    assert len(store.read_trace("c-031")) == 1
    assert store.read_trace("c-030")[0]["status"] == "success"
    assert store.read_trace("c-031")[0]["status"] == "failed"


# ---------------------------------------------------------------------------
# read_trace edge cases
# ---------------------------------------------------------------------------

def test_read_trace_returns_empty_for_unknown_claim(store: TraceStore) -> None:
    assert store.read_trace("nonexistent") == []


def test_read_trace_timestamp_present(store: TraceStore) -> None:
    store.record_node("c-040", "router", 1, "success", 10, 0.0)
    events = store.read_trace("c-040")
    assert "timestamp" in events[0]
