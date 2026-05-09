"""
Static DAG definition for the VeriClaim orchestration graph.

The graph is encoded as {node_name: [dependency_names]}.
The orchestrator derives parallel execution stages from a topological sort.
No node decides what happens next — the orchestrator is the only coordinator.
"""
from __future__ import annotations

from collections import defaultdict, deque

# Adjacency list: node → its upstream dependencies
GRAPH: dict[str, list[str]] = {
    "router": [],
    "damage_assessor": ["router"],
    "document_extractor": ["router"],
    "statement_analyst": ["router"],
    "policy_reasoner": ["damage_assessor", "document_extractor", "statement_analyst"],
    "fraud_aggregator": ["damage_assessor", "document_extractor", "statement_analyst"],
    "consistency_auditor": ["damage_assessor", "document_extractor", "statement_analyst"],
    "adjudicator": ["policy_reasoner", "fraud_aggregator", "consistency_auditor"],
    "output_drafter": ["adjudicator"],
}

# Stage-2 specialists that operate on raw inputs in parallel
EVIDENCE_STAGE: frozenset[str] = frozenset(
    {"damage_assessor", "document_extractor", "statement_analyst"}
)

# Stage-3 specialists that operate on the EvidenceStore in parallel
REASONING_STAGE: frozenset[str] = frozenset(
    {"policy_reasoner", "fraud_aggregator", "consistency_auditor"}
)


def topological_stages() -> list[list[str]]:
    """
    Return execution stages: each stage is a list of nodes that can run in parallel
    because all their dependencies are satisfied by prior stages.

    Example output:
        [["router"],
         ["damage_assessor", "document_extractor", "statement_analyst"],
         ["policy_reasoner", "fraud_aggregator", "consistency_auditor"],
         ["adjudicator"],
         ["output_drafter"]]
    """
    in_degree: dict[str, int] = {node: len(deps) for node, deps in GRAPH.items()}
    dependents: dict[str, list[str]] = defaultdict(list)
    for node, deps in GRAPH.items():
        for dep in deps:
            dependents[dep].append(node)

    queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
    stages: list[list[str]] = []

    while queue:
        stage = list(queue)
        queue.clear()
        stages.append(sorted(stage))  # sort for deterministic ordering

        next_ready: list[str] = []
        for node in stage:
            for dependent in dependents[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_ready.append(dependent)
        queue.extend(next_ready)

    if sum(len(s) for s in stages) != len(GRAPH):
        raise RuntimeError("Cycle detected in orchestration graph — check graph.py")

    return stages


# Eagerly validate the graph on import
_STAGES = topological_stages()
