from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SuiteResult:
    suite_name: str
    dataset_path: Path
    metrics: dict[str, float] = field(default_factory=dict)
    cost_usd: float = 0.0
    latency_p50_ms: int = 0
    latency_p95_ms: int = 0
    n_samples: int = 0
    n_failures: int = 0
    prompt_hashes: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""

    def delta(self, baseline: "SuiteResult") -> dict[str, float]:
        """Return metric deltas vs a baseline result (positive = improvement)."""
        deltas: dict[str, float] = {}
        for k, v in self.metrics.items():
            if k in baseline.metrics:
                deltas[k] = v - baseline.metrics[k]
        return deltas

    def to_changelog_entry(self, change_description: str, decision: str) -> str:
        """Format as a CHANGELOG.md entry."""
        date = self.timestamp.strftime("%Y-%m-%d")
        metric_summary = ", ".join(f"{k}={v:.3f}" for k, v in self.metrics.items())
        return (
            f"## {date} | {change_description} | {metric_summary} | {decision}"
        )
