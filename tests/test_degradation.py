from orchestration.failure.degradation import format_degradation_block, get_degraded_context
from orchestration.state import AgentStatus, EvidenceStore


def _store_with(*agent_statuses: tuple[str, AgentStatus]) -> EvidenceStore:
    store = EvidenceStore(claim_id="test-001")
    for name, status in agent_statuses:
        store = store.mark_agent(name, status)
    return store


# ---------------------------------------------------------------------------
# get_degraded_context — what's returned
# ---------------------------------------------------------------------------

def test_no_amendments_when_all_succeed() -> None:
    store = _store_with(
        ("damage_assessor", AgentStatus.SUCCESS),
        ("document_extractor", AgentStatus.SUCCESS),
    )
    assert get_degraded_context(store) == {}


def test_amendment_for_failed_damage_assessor() -> None:
    store = _store_with(("damage_assessor", AgentStatus.FAILED))
    ctx = get_degraded_context(store)
    assert "damage_assessor" in ctx
    assert "HUMAN_REVIEW" in ctx["damage_assessor"]


def test_amendment_for_timed_out_agent() -> None:
    store = _store_with(("policy_reasoner", AgentStatus.TIMEOUT))
    ctx = get_degraded_context(store)
    assert "policy_reasoner" in ctx


def test_amendment_for_partial_damage_assessor() -> None:
    store = _store_with(("damage_assessor", AgentStatus.PARTIAL))
    ctx = get_degraded_context(store)
    assert "damage_assessor" in ctx
    # Partial message should be less severe — no HUMAN_REVIEW mandate
    assert "lower confidence" in ctx["damage_assessor"]


def test_skipped_agents_produce_no_amendment() -> None:
    store = _store_with(("statement_analyst", AgentStatus.SKIPPED))
    ctx = get_degraded_context(store)
    assert "statement_analyst" not in ctx


def test_multiple_failures_produce_multiple_amendments() -> None:
    store = _store_with(
        ("damage_assessor", AgentStatus.FAILED),
        ("document_extractor", AgentStatus.FAILED),
        ("policy_reasoner", AgentStatus.SUCCESS),
    )
    ctx = get_degraded_context(store)
    assert "damage_assessor" in ctx
    assert "document_extractor" in ctx
    assert "policy_reasoner" not in ctx


def test_amendment_content_specific_to_agent() -> None:
    damage_store = _store_with(("damage_assessor", AgentStatus.FAILED))
    fraud_store = _store_with(("fraud_aggregator", AgentStatus.FAILED))

    damage_ctx = get_degraded_context(damage_store)
    fraud_ctx = get_degraded_context(fraud_store)

    # Messages should be agent-specific, not identical
    assert damage_ctx["damage_assessor"] != fraud_ctx["fraud_aggregator"]


# ---------------------------------------------------------------------------
# format_degradation_block
# ---------------------------------------------------------------------------

def test_empty_block_when_no_failures() -> None:
    store = _store_with(("damage_assessor", AgentStatus.SUCCESS))
    assert format_degradation_block(store) == ""


def test_block_contains_header_when_failures_present() -> None:
    store = _store_with(("damage_assessor", AgentStatus.FAILED))
    block = format_degradation_block(store)
    assert "UPSTREAM SPECIALIST STATUS" in block


def test_block_contains_amendment_text() -> None:
    store = _store_with(("fraud_aggregator", AgentStatus.FAILED))
    block = format_degradation_block(store)
    assert "fraud" in block.lower()


def test_block_contains_all_amendments() -> None:
    store = _store_with(
        ("damage_assessor", AgentStatus.FAILED),
        ("document_extractor", AgentStatus.TIMEOUT),
    )
    block = format_degradation_block(store)
    assert "damage" in block.lower()
    assert "document" in block.lower()
