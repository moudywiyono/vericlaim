"""
Component eval runner — evaluates a single specialist agent in isolation.

The EvidenceStore boundary makes this clean: populate the ClaimPacket from a
sample manifest, run the target node, compare output findings to ground_truth.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from evals.runners.base import SuiteResult
from orchestration.nodes.base import Node
from orchestration.state import AgentStatus, EvidenceStore

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

# Agents with implemented eval scoring (others raise NotImplementedError)
_SCORED_AGENTS = {"damage_assessor", "document_extractor"}


class ComponentSuite:
    """
    Runs a labeled dataset against a single specialist agent.

    Dataset layout:
        dataset_path/
          sample_001/
            manifest.json       — standard claim manifest
            ground_truth.json   — expected findings (schema below)
          sample_002/
            ...

    ground_truth.json schema:
      damage_assessor:
        {"expected_categories": ["moderate", "cosmetic"],
         "expected_cost_by_region": {"front_bumper": 1200.0}}
      document_extractor:
        {"expected_fields": {"date_of_loss": "2024-03-15", "claimant_name": "John Smith"}}
    """

    def __init__(self, agent_name: str, dataset_path: Path) -> None:
        if agent_name not in SUPPORTED_AGENTS:
            raise ValueError(f"Unknown agent: {agent_name}. Must be one of {SUPPORTED_AGENTS}")
        self.agent_name = agent_name
        self.dataset_path = dataset_path

    def run(self) -> SuiteResult:
        """
        Execute the component eval suite.

        For each sample: load manifest → run node → score against ground_truth.json.
        Returns a SuiteResult with per-metric averages across all samples.
        """
        samples = sorted(p for p in self.dataset_path.iterdir() if p.is_dir())
        if not samples:
            raise ValueError(f"No samples found in {self.dataset_path}")

        node = self._get_node()
        all_metrics: dict[str, list[float]] = {}
        total_cost = 0.0
        latencies: list[int] = []
        n_failures = 0

        for sample_dir in samples:
            from ingestion.intake import load_claim_from_manifest
            packet = load_claim_from_manifest(sample_dir)
            gt_path = sample_dir / "ground_truth.json"
            ground_truth = json.loads(gt_path.read_text()) if gt_path.exists() else {}

            store = EvidenceStore(claim_id=packet.claim_id)
            start = time.monotonic()
            try:
                result = asyncio.run(node.run(store, packet))
                elapsed_ms = int((time.monotonic() - start) * 1000)
                latencies.append(elapsed_ms)
                total_cost += result.cost_usd

                if result.status in (AgentStatus.FAILED, AgentStatus.TIMEOUT):
                    n_failures += 1

                for k, v in self._score(result.store, ground_truth).items():
                    all_metrics.setdefault(k, []).append(v)

            except Exception as e:
                logger.error("Sample %s failed: %s", sample_dir.name, e)
                n_failures += 1
                latencies.append(int((time.monotonic() - start) * 1000))

        agg_metrics = {k: sum(v) / len(v) for k, v in all_metrics.items() if v}
        latencies_sorted = sorted(latencies)
        p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0
        p95_idx = min(int(len(latencies_sorted) * 0.95), len(latencies_sorted) - 1)
        p95 = latencies_sorted[p95_idx] if latencies_sorted else 0

        return SuiteResult(
            suite_name=f"{self.agent_name}_component_eval",
            dataset_path=self.dataset_path,
            metrics=agg_metrics,
            cost_usd=total_cost,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            n_samples=len(samples),
            n_failures=n_failures,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_node(self) -> Node:
        if self.agent_name == "damage_assessor":
            from orchestration.nodes.damage_assessor import DamageAssessorNode
            return DamageAssessorNode()
        if self.agent_name == "document_extractor":
            from orchestration.nodes.document_extractor import DocumentExtractorNode
            return DocumentExtractorNode()
        raise NotImplementedError(
            f"Component eval for '{self.agent_name}' not yet implemented (Phase 3+)"
        )

    def _score(self, store: EvidenceStore, ground_truth: dict) -> dict[str, float]:
        if self.agent_name == "damage_assessor":
            return self._score_damage(store, ground_truth)
        if self.agent_name == "document_extractor":
            return self._score_documents(store, ground_truth)
        return {}

    def _score_damage(self, store: EvidenceStore, ground_truth: dict) -> dict[str, float]:
        from evals.metrics.damage_metrics import macro_f1_severity, mape_by_damage_type

        metrics: dict[str, float] = {}

        expected_categories = ground_truth.get("expected_categories", [])
        if expected_categories and store.damage_findings:
            predicted = [f.category for f in store.damage_findings]
            n = min(len(predicted), len(expected_categories))
            metrics["macro_f1_severity"] = macro_f1_severity(
                predicted[:n], expected_categories[:n]
            )

        expected_costs = ground_truth.get("expected_cost_by_region", {})
        if expected_costs and store.damage_findings:
            pred_costs: dict[str, list[float]] = {}
            gt_costs: dict[str, list[float]] = {}
            for f in store.damage_findings:
                if f.region_id in expected_costs:
                    pred_costs.setdefault(f.region_id, []).append(f.estimated_cost_usd)
                    gt_costs.setdefault(f.region_id, []).append(expected_costs[f.region_id])
            if pred_costs:
                mape_result = mape_by_damage_type(pred_costs, gt_costs)
                if mape_result:
                    metrics["mape_cost"] = sum(mape_result.values()) / len(mape_result)

        return metrics

    def _score_documents(self, store: EvidenceStore, ground_truth: dict) -> dict[str, float]:
        from evals.metrics.document_metrics import anls_score, field_exact_match

        expected_fields = ground_truth.get("expected_fields", {})
        if not expected_fields:
            return {}

        predicted = {f.field_name: f.value for f in store.document_findings}
        metrics: dict[str, float] = {
            "field_exact_match": field_exact_match(predicted, expected_fields),
        }

        common = [k for k in expected_fields if k in predicted]
        if common:
            metrics["anls"] = anls_score(
                [predicted[k] for k in common],
                [expected_fields[k] for k in common],
            )

        return metrics
