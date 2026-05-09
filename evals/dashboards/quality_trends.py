"""
Dashboard 2 — Quality Trends (weekly).

Reads serialized SuiteResult JSON files from a results directory and computes:
  - Per-metric trend over time
  - Per-sub-population (claim_type) breakdown
  - Citation correctness from trace metadata
  - LLM judge score averages (when present in result files)

SuiteResult files are written by evals.runners after each run:
    results/<suite_name>/<timestamp>.json

CLI:
    python -m evals.dashboards.quality_trends [--results-dir eval-results/]
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MetricTrendPoint:
    timestamp: str
    suite_name: str
    metrics: dict[str, float]
    cost_usd: float
    n_samples: int
    n_failures: int
    prompt_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class QualityTrendsReport:
    # chronological list of data points per suite
    trends: dict[str, list[MetricTrendPoint]] = field(default_factory=dict)
    # latest metric values per suite
    latest: dict[str, dict[str, float]] = field(default_factory=dict)
    # latest metric breakdown by claim_type (sub-population)
    by_claim_type: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "latest": self.latest,
            "by_claim_type": self.by_claim_type,
            "trends": {
                suite: [
                    {
                        "timestamp": pt.timestamp,
                        "metrics": {k: round(v, 4) for k, v in pt.metrics.items()},
                        "cost_usd": round(pt.cost_usd, 6),
                        "n_samples": pt.n_samples,
                        "n_failures": pt.n_failures,
                        "prompt_hashes": pt.prompt_hashes,
                    }
                    for pt in points
                ]
                for suite, points in self.trends.items()
            },
        }


def quality_trends(results_dir: Path | str = "eval-results") -> QualityTrendsReport:
    """
    Aggregate quality trends from serialized SuiteResult JSON files.

    Expected file layout:
        results_dir/<suite_name>/<ISO-timestamp>.json
    or flat:
        results_dir/<suite_name>-<timestamp>.json

    Each JSON file must have the fields produced by SuiteResult (suite_name,
    metrics, cost_usd, n_samples, n_failures, prompt_hashes, timestamp).
    """
    results_dir = Path(results_dir)
    if not results_dir.exists():
        return QualityTrendsReport()

    trends: dict[str, list[MetricTrendPoint]] = defaultdict(list)
    by_claim_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for json_file in sorted(results_dir.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        suite_name = data.get("suite_name", json_file.stem)
        timestamp = data.get("timestamp", "")
        metrics = data.get("metrics", {})
        cost = data.get("cost_usd", 0.0)
        n_samples = data.get("n_samples", 0)
        n_failures = data.get("n_failures", 0)
        prompt_hashes = data.get("prompt_hashes", {})

        pt = MetricTrendPoint(
            timestamp=timestamp,
            suite_name=suite_name,
            metrics=metrics,
            cost_usd=cost,
            n_samples=n_samples,
            n_failures=n_failures,
            prompt_hashes=prompt_hashes,
        )
        trends[suite_name].append(pt)

        # sub-population breakdown stored as metrics prefixed with "claim_type_<type>_"
        for key, val in metrics.items():
            if key.startswith("claim_type_"):
                parts = key.split("_", 3)
                if len(parts) == 4:
                    ct = parts[2]
                    metric_name = parts[3]
                    by_claim_type[ct][metric_name].append(val)

    # sort trends chronologically
    for suite in trends:
        trends[suite].sort(key=lambda p: p.timestamp)

    latest = {
        suite: points[-1].metrics
        for suite, points in trends.items()
        if points
    }

    aggregated_by_ct = {
        ct: {metric: sum(vals) / len(vals) for metric, vals in m.items()}
        for ct, m in by_claim_type.items()
    }

    return QualityTrendsReport(
        trends=dict(trends),
        latest=latest,
        by_claim_type=aggregated_by_ct,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quality trends dashboard")
    parser.add_argument("--results-dir", default=os.getenv("VERICLAIM_RESULTS_DIR", "eval-results"))
    args = parser.parse_args()

    report = quality_trends(args.results_dir)
    print(json.dumps(report.to_dict(), indent=2))
