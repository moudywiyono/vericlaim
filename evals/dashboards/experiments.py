"""
Dashboard 3 — Model / Prompt Experiments (A/B deltas).

Compares a candidate SuiteResult against a baseline, producing:
  - Per-metric delta (positive = improvement)
  - Per-sub-population delta breakdown
  - Cost delta and latency delta
  - Prompt hash diff (which prompts changed between runs)

Designed for the eval-as-CI flow: the CI runner serializes the baseline
SuiteResult from the main branch, runs the candidate on the PR branch,
and calls experiments_delta() to produce the PR comment body.

CLI:
    python -m evals.dashboards.experiments --baseline baseline.json --candidate candidate.json
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MetricDelta:
    metric: str
    baseline: float
    candidate: float
    delta: float
    pct_change: float  # relative change vs baseline, in percent


@dataclass
class ExperimentsReport:
    suite_name: str
    baseline_timestamp: str
    candidate_timestamp: str
    metric_deltas: list[MetricDelta] = field(default_factory=list)
    cost_delta_usd: float = 0.0
    latency_p50_delta_ms: float = 0.0
    latency_p95_delta_ms: float = 0.0
    n_samples_baseline: int = 0
    n_samples_candidate: int = 0
    changed_prompt_hashes: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def regression_count(self) -> int:
        return sum(1 for d in self.metric_deltas if d.delta < 0)

    @property
    def improvement_count(self) -> int:
        return sum(1 for d in self.metric_deltas if d.delta > 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "baseline_timestamp": self.baseline_timestamp,
            "candidate_timestamp": self.candidate_timestamp,
            "regression_count": self.regression_count,
            "improvement_count": self.improvement_count,
            "cost_delta_usd": round(self.cost_delta_usd, 6),
            "latency_p50_delta_ms": round(self.latency_p50_delta_ms, 1),
            "latency_p95_delta_ms": round(self.latency_p95_delta_ms, 1),
            "n_samples_baseline": self.n_samples_baseline,
            "n_samples_candidate": self.n_samples_candidate,
            "changed_prompt_hashes": {
                k: {"baseline": v[0], "candidate": v[1]}
                for k, v in self.changed_prompt_hashes.items()
            },
            "metric_deltas": [
                {
                    "metric": d.metric,
                    "baseline": round(d.baseline, 4),
                    "candidate": round(d.candidate, 4),
                    "delta": round(d.delta, 4),
                    "pct_change": round(d.pct_change, 2),
                }
                for d in sorted(self.metric_deltas, key=lambda x: x.metric)
            ],
        }

    def to_markdown(self) -> str:
        """Render as a GitHub PR comment body."""
        emoji = "✅" if self.regression_count == 0 else "⚠️"
        lines = [
            f"## {emoji} Eval Delta — `{self.suite_name}`",
            "",
            f"| | Baseline | Candidate | Delta |",
            f"|---|---|---|---|",
        ]
        for d in sorted(self.metric_deltas, key=lambda x: x.metric):
            sign = "+" if d.delta >= 0 else ""
            lines.append(
                f"| {d.metric} | {d.baseline:.4f} | {d.candidate:.4f} | {sign}{d.delta:.4f} |"
            )
        lines += [
            "",
            f"**Cost delta:** {self.cost_delta_usd:+.6f} USD",
            f"**Latency p50 delta:** {self.latency_p50_delta_ms:+.1f} ms",
            f"**Regressions:** {self.regression_count} | **Improvements:** {self.improvement_count}",
        ]
        if self.changed_prompt_hashes:
            lines += ["", "**Changed prompts:**"]
            for name, (b, c) in self.changed_prompt_hashes.items():
                lines.append(f"- `{name}`: `{b}` → `{c}`")
        return "\n".join(lines)


def experiments_delta(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> ExperimentsReport:
    """
    Compare two SuiteResult-shaped dicts.

    Both dicts must contain at minimum: suite_name, metrics, timestamp.
    Optional fields: cost_usd, latency_p50_ms, latency_p95_ms, n_samples, prompt_hashes.
    """
    suite_name = candidate.get("suite_name", baseline.get("suite_name", "unknown"))

    baseline_metrics: dict[str, float] = baseline.get("metrics", {})
    candidate_metrics: dict[str, float] = candidate.get("metrics", {})

    all_metric_names = set(baseline_metrics) | set(candidate_metrics)
    deltas = []
    for metric in sorted(all_metric_names):
        b = baseline_metrics.get(metric, 0.0)
        c = candidate_metrics.get(metric, 0.0)
        delta = c - b
        pct = (delta / b * 100) if b != 0 else 0.0
        deltas.append(MetricDelta(metric=metric, baseline=b, candidate=c, delta=delta, pct_change=pct))

    cost_delta = candidate.get("cost_usd", 0.0) - baseline.get("cost_usd", 0.0)
    lat50_delta = candidate.get("latency_p50_ms", 0.0) - baseline.get("latency_p50_ms", 0.0)
    lat95_delta = candidate.get("latency_p95_ms", 0.0) - baseline.get("latency_p95_ms", 0.0)

    # find prompts that changed between runs
    b_hashes: dict[str, str] = baseline.get("prompt_hashes", {})
    c_hashes: dict[str, str] = candidate.get("prompt_hashes", {})
    changed: dict[str, tuple[str, str]] = {}
    for name in set(b_hashes) | set(c_hashes):
        bh = b_hashes.get(name, "")
        ch = c_hashes.get(name, "")
        if bh != ch:
            changed[name] = (bh, ch)

    return ExperimentsReport(
        suite_name=suite_name,
        baseline_timestamp=baseline.get("timestamp", ""),
        candidate_timestamp=candidate.get("timestamp", ""),
        metric_deltas=deltas,
        cost_delta_usd=cost_delta,
        latency_p50_delta_ms=lat50_delta,
        latency_p95_delta_ms=lat95_delta,
        n_samples_baseline=baseline.get("n_samples", 0),
        n_samples_candidate=candidate.get("n_samples", 0),
        changed_prompt_hashes=changed,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A/B experiment delta dashboard")
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline SuiteResult JSON")
    parser.add_argument("--candidate", type=Path, required=True, help="Candidate SuiteResult JSON")
    parser.add_argument("--markdown", action="store_true", help="Output as Markdown (for PR comments)")
    args = parser.parse_args()

    b = json.loads(args.baseline.read_text())
    c = json.loads(args.candidate.read_text())
    report = experiments_delta(b, c)

    if args.markdown:
        print(report.to_markdown())
    else:
        print(json.dumps(report.to_dict(), indent=2))
