"""
Component eval runner — evaluates a single specialist agent in isolation.

The EvidenceStore boundary makes this clean: populate EvidenceStore directly
(bypassing upstream specialists), run the target agent, measure its output.
"""
from __future__ import annotations

import logging
from pathlib import Path

from evals.runners.base import SuiteResult

logger = logging.getLogger(__name__)

SUPPORTED_AGENTS = {
    "damage_assessor",
    "document_extractor",
    "statement_analyst",
    "policy_reasoner",
    "fraud_aggregator",
    "consistency_auditor",
    "adjudicator",
    "output_drafter",
}


class ComponentSuite:
    """
    Runs a labeled dataset against a single specialist agent.

    Args:
        agent_name: must be one of SUPPORTED_AGENTS
        dataset_path: directory containing per-sample subdirs, each with manifest.json
                      and a ground_truth.json with expected outputs
    """

    def __init__(self, agent_name: str, dataset_path: Path) -> None:
        if agent_name not in SUPPORTED_AGENTS:
            raise ValueError(f"Unknown agent: {agent_name}. Must be one of {SUPPORTED_AGENTS}")
        self.agent_name = agent_name
        self.dataset_path = dataset_path

    def run(self) -> SuiteResult:
        """
        Execute the component eval suite.

        For each sample in dataset_path:
        1. Load the pre-populated EvidenceStore from ground_truth.json (mocked upstream)
        2. Run the target agent
        3. Compare output to expected findings
        4. Compute agent-appropriate metrics

        Returns SuiteResult with metrics populated.
        """
        raise NotImplementedError
