"""
Dashboard 1 — System Health (daily).

Reads all JSONL trace files in the trace directory and computes:
  - End-to-end latency percentiles (p50, p95, p99)
  - Per-node latency percentiles
  - Per-node error rate
  - Cost per claim (mean, p95)
  - Auto-approve rate: COMPLETE / (COMPLETE + HUMAN_REVIEW)

CLI:
    python -m evals.dashboards.system_health [--trace-dir traces/]
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
class SystemHealthReport:
    n_claims: int = 0
    auto_approve_rate: float = 0.0
    human_review_rate: float = 0.0
    e2e_latency_p50_ms: float = 0.0
    e2e_latency_p95_ms: float = 0.0
    e2e_latency_p99_ms: float = 0.0
    cost_per_claim_mean_usd: float = 0.0
    cost_per_claim_p95_usd: float = 0.0
    error_rate: float = 0.0
    per_node_latency_p50_ms: dict[str, float] = field(default_factory=dict)
    per_node_latency_p95_ms: dict[str, float] = field(default_factory=dict)
    per_node_error_rate: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_claims": self.n_claims,
            "auto_approve_rate": round(self.auto_approve_rate, 4),
            "human_review_rate": round(self.human_review_rate, 4),
            "e2e_latency_p50_ms": round(self.e2e_latency_p50_ms, 1),
            "e2e_latency_p95_ms": round(self.e2e_latency_p95_ms, 1),
            "e2e_latency_p99_ms": round(self.e2e_latency_p99_ms, 1),
            "cost_per_claim_mean_usd": round(self.cost_per_claim_mean_usd, 6),
            "cost_per_claim_p95_usd": round(self.cost_per_claim_p95_usd, 6),
            "error_rate": round(self.error_rate, 4),
            "per_node_latency_p50_ms": {k: round(v, 1) for k, v in self.per_node_latency_p50_ms.items()},
            "per_node_latency_p95_ms": {k: round(v, 1) for k, v in self.per_node_latency_p95_ms.items()},
            "per_node_error_rate": {k: round(v, 4) for k, v in self.per_node_error_rate.items()},
        }


def system_health(trace_dir: Path | str = "traces") -> SystemHealthReport:
    """Aggregate system health metrics from JSONL trace files."""
    trace_dir = Path(trace_dir)
    if not trace_dir.exists():
        return SystemHealthReport()

    # Accumulators keyed by claim_id
    claim_node_latencies: dict[str, list[int]] = defaultdict(list)
    claim_costs: dict[str, float] = defaultdict(float)
    claim_final_states: dict[str, str] = {}
    claim_had_error: dict[str, bool] = defaultdict(bool)

    per_node_latencies: dict[str, list[int]] = defaultdict(list)
    per_node_errors: dict[str, list[bool]] = defaultdict(list)

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
                elapsed = event.get("elapsed_ms", 0)
                cost = event.get("cost_usd", 0.0)
                status = event.get("status", "")

                claim_node_latencies[claim_id].append(elapsed)
                claim_costs[claim_id] += cost
                per_node_latencies[node].append(elapsed)

                is_error = status in ("failed", "timeout")
                per_node_errors[node].append(is_error)
                if is_error:
                    claim_had_error[claim_id] = True

            elif event_type == "llm_generation":
                claim_costs[claim_id] += event.get("cost_usd", 0.0)

            elif event_type == "claim_state_transition":
                state = event.get("state", "")
                if state in ("complete", "human_review", "failed"):
                    claim_final_states[claim_id] = state

    all_claim_ids = set(claim_node_latencies) | set(claim_costs)
    n_claims = len(all_claim_ids)
    if n_claims == 0:
        return SystemHealthReport()

    e2e_latencies = [sum(claim_node_latencies[cid]) for cid in all_claim_ids]
    costs = [claim_costs[cid] for cid in all_claim_ids]
    n_errors = sum(1 for cid in all_claim_ids if claim_had_error.get(cid, False))

    terminal_states = list(claim_final_states.values())
    n_complete = terminal_states.count("complete")
    n_human = terminal_states.count("human_review")
    denom = n_complete + n_human
    auto_approve = n_complete / denom if denom else 0.0
    human_review = n_human / denom if denom else 0.0

    return SystemHealthReport(
        n_claims=n_claims,
        auto_approve_rate=auto_approve,
        human_review_rate=human_review,
        e2e_latency_p50_ms=_percentile(e2e_latencies, 50),
        e2e_latency_p95_ms=_percentile(e2e_latencies, 95),
        e2e_latency_p99_ms=_percentile(e2e_latencies, 99),
        cost_per_claim_mean_usd=sum(costs) / len(costs) if costs else 0.0,
        cost_per_claim_p95_usd=_percentile(costs, 95),
        error_rate=n_errors / n_claims,
        per_node_latency_p50_ms={
            node: _percentile(lats, 50) for node, lats in per_node_latencies.items()
        },
        per_node_latency_p95_ms={
            node: _percentile(lats, 95) for node, lats in per_node_latencies.items()
        },
        per_node_error_rate={
            node: sum(errs) / len(errs) for node, errs in per_node_errors.items() if errs
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="System health dashboard")
    parser.add_argument("--trace-dir", default=os.getenv("VERICLAIM_TRACE_DIR", "traces"))
    args = parser.parse_args()

    report = system_health(args.trace_dir)
    print(json.dumps(report.to_dict(), indent=2))
