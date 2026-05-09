import pytest

from orchestration.graph import EVIDENCE_STAGE, GRAPH, REASONING_STAGE, topological_stages


# ---------------------------------------------------------------------------
# Graph structure
# ---------------------------------------------------------------------------

def test_all_expected_nodes_present() -> None:
    expected = {
        "router",
        "damage_assessor",
        "document_extractor",
        "statement_analyst",
        "policy_reasoner",
        "fraud_aggregator",
        "consistency_auditor",
        "adjudicator",
        "output_drafter",
    }
    assert set(GRAPH.keys()) == expected


def test_router_has_no_dependencies() -> None:
    assert GRAPH["router"] == []


def test_adjudicator_depends_on_all_reasoning_agents() -> None:
    assert set(GRAPH["adjudicator"]) == {"policy_reasoner", "fraud_aggregator", "consistency_auditor"}


def test_output_drafter_depends_only_on_adjudicator() -> None:
    assert GRAPH["output_drafter"] == ["adjudicator"]


def test_evidence_agents_depend_only_on_router() -> None:
    for agent in ["damage_assessor", "document_extractor", "statement_analyst"]:
        assert GRAPH[agent] == ["router"]


def test_reasoning_agents_depend_on_all_evidence_agents() -> None:
    evidence = {"damage_assessor", "document_extractor", "statement_analyst"}
    for agent in ["policy_reasoner", "fraud_aggregator", "consistency_auditor"]:
        assert set(GRAPH[agent]) == evidence


# ---------------------------------------------------------------------------
# topological_stages — structure
# ---------------------------------------------------------------------------

def test_produces_five_stages() -> None:
    stages = topological_stages()
    assert len(stages) == 5


def test_stage_0_is_router() -> None:
    stages = topological_stages()
    assert stages[0] == ["router"]


def test_stage_1_is_evidence_agents() -> None:
    stages = topological_stages()
    assert set(stages[1]) == {"damage_assessor", "document_extractor", "statement_analyst"}


def test_stage_2_is_reasoning_agents() -> None:
    stages = topological_stages()
    assert set(stages[2]) == {"policy_reasoner", "fraud_aggregator", "consistency_auditor"}


def test_stage_3_is_adjudicator() -> None:
    stages = topological_stages()
    assert stages[3] == ["adjudicator"]


def test_stage_4_is_output_drafter() -> None:
    stages = topological_stages()
    assert stages[4] == ["output_drafter"]


def test_all_nodes_appear_exactly_once() -> None:
    stages = topological_stages()
    all_nodes = [n for stage in stages for n in stage]
    assert len(all_nodes) == len(GRAPH)
    assert set(all_nodes) == set(GRAPH.keys())


def test_stages_are_sorted_deterministically() -> None:
    # Running twice should produce identical output
    assert topological_stages() == topological_stages()


# ---------------------------------------------------------------------------
# Stage set constants
# ---------------------------------------------------------------------------

def test_evidence_stage_constant_matches_graph() -> None:
    deps_of_reasoning = set(GRAPH["policy_reasoner"])
    assert EVIDENCE_STAGE == deps_of_reasoning


def test_reasoning_stage_constant_matches_graph() -> None:
    deps_of_adjudicator = set(GRAPH["adjudicator"])
    assert REASONING_STAGE == deps_of_adjudicator


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

def test_cycle_detection_raises_on_bad_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that a graph with a cycle raises RuntimeError, not hangs."""
    import orchestration.graph as graph_module

    cyclic = {
        "a": ["b"],
        "b": ["a"],
    }
    monkeypatch.setattr(graph_module, "GRAPH", cyclic)
    with pytest.raises(RuntimeError, match="Cycle detected"):
        graph_module.topological_stages()
