"""
Dashboard 4 — Cost & Latency Deep-Dive.

Per-node and per-model breakdown of cost and latency from JSONL traces.
Produces cost-vs-latency scatter data and Pareto rankings.

CLI:
    python -m evals.dashboards.cost_latency [--trace-dir traces/]
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = min(int(len(sorted_v) * p / 100), len(sorted_v) - 1)
    return sorted_v[idx]


@dataclass
class NodeCostLatency:
    node_name: str
    n_calls: int = 0
    total_cost_usd: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    cost_per_call_mean_usd: float = 0.0


@dataclass
class ModelCostLatency:
    model: str
    n_calls: int = 0
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cost_per_1k_tokens_usd: float = 0.0


@dataclass
class CostLatencyReport:
    total_cost_usd: float = 0.0
    total_claims: int = 0
    per_node: list[NodeCostLatency] = field(default_factory=list)
    per_model: list[ModelCostLatency] = field(default_factory=list)
    # scatter: list of (cost_usd, latency_ms) per claim for plotting
    claim_scatter: list[dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_claims": self.total_claims,
            "per_node": [
                {
                    "node": n.node_name,
                    "n_calls": n.n_calls,
                    "total_cost_usd": round(n.total_cost_usd, 6),
                    "latency_p50_ms": round(n.latency_p50_ms, 1),
                    "latency_p95_ms": round(n.latency_p95_ms, 1),
                    "cost_per_call_mean_usd": round(n.cost_per_call_mean_usd, 6),
                }
                for n in sorted(self.per_node, key=lambda x: x.total_cost_usd, reverse=True)
            ],
            "per_model": [
                {
                    "model": m.model,
                    "n_calls": m.n_calls,
                    "total_cost_usd": round(m.total_cost_usd, 6),
                    "total_input_tokens": m.total_input_tokens,
                    "total_output_tokens": m.total_output_tokens,
                    "cost_per_1k_tokens_usd": round(m.cost_per_1k_tokens_usd, 6),
                }
                for m in sorted(self.per_model, key=lambda x: x.total_cost_usd, reverse=True)
            ],
            "claim_scatter": self.claim_scatter[:200],  # cap for serialization
        }


def cost_latency(trace_dir: Path | str = "traces") -> CostLatencyReport:
    """Aggregate cost and latency metrics from JSONL trace files."""
    trace_dir = Path(trace_dir)
    if not trace_dir.exists():
        return CostLatencyReport()

    node_latencies: dict[str, list[float]] = defaultdict(list)
    node_costs: dict[str, list[float]] = defaultdict(list)

    model_calls: dict[str, int] = defaultdict(int)
    model_costs: dict[str, float] = defaultdict(float)
    model_input_tokens: dict[str, int] = defaultdict(int)
    model_output_tokens: dict[str, int] = defaultdict(int)

    claim_costs: dict[str, float] = defaultdict(float)
    claim_latencies: dict[str, float] = defaultdict(float)

    for trace_file in trace_dir.glob("*.jsonl"):
        for line in trace_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            claim_id = event.get("claim_id", "")
            event_type = event.get("event", "")

            if event_type == "node_execution":
                node = event.get("node_name", "unknown")
                elapsed = float(event.get("elapsed_ms", 0))
                cost = float(event.get("cost_usd", 0.0))
                node_latencies[node].append(elapsed)
                node_costs[node].append(cost)
                claim_latencies[claim_id] += elapsed
                claim_costs[claim_id] += cost

                # capture model_used from node_execution metadata when present
                model = event.get("model_used") or (event.get("metadata") or {}).get("model_used")
                if model:
                    model_calls[model] += 1
                    model_costs[model] += cost

            elif event_type == "llm_generation":
                model = event.get("model", "unknown")
                cost = float(event.get("cost_usd", 0.0))
                inp = int(event.get("input_tokens", 0))
                out = int(event.get("output_tokens", 0))
                model_calls[model] += 1
                model_costs[model] += cost
                model_input_tokens[model] += inp
                model_output_tokens[model] += out
                claim_costs[claim_id] += cost

    per_node = [
        NodeCostLatency(
            node_name=node,
            n_calls=len(lats),
            total_cost_usd=sum(node_costs[node]),
            latency_p50_ms=_percentile(lats, 50),
            latency_p95_ms=_percentile(lats, 95),
            cost_per_call_mean_usd=sum(node_costs[node]) / len(node_costs[node]) if node_costs[node] else 0.0,
        )
        for node, lats in node_latencies.items()
    ]

    per_model = []
    for model, calls in model_calls.items():
        total_tok = model_input_tokens[model] + model_output_tokens[model]
        per_model.append(ModelCostLatency(
            model=model,
            n_calls=calls,
            total_cost_usd=model_costs[model],
            total_input_tokens=model_input_tokens[model],
            total_output_tokens=model_output_tokens[model],
            cost_per_1k_tokens_usd=model_costs[model] / (total_tok / 1000) if total_tok else 0.0,
        ))

    all_claim_ids = set(claim_costs) | set(claim_latencies)
    scatter = [
        {"cost_usd": round(claim_costs[cid], 6), "latency_ms": round(claim_latencies[cid], 1)}
        for cid in all_claim_ids
    ]

    return CostLatencyReport(
        total_cost_usd=sum(claim_costs.values()),
        total_claims=len(all_claim_ids),
        per_node=per_node,
        per_model=per_model,
        claim_scatter=scatter,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cost & latency deep-dive dashboard")
    parser.add_argument("--trace-dir", default=os.getenv("VERICLAIM_TRACE_DIR", "traces"))
    args = parser.parse_args()

    report = cost_latency(args.trace_dir)
    print(json.dumps(report.to_dict(), indent=2))
