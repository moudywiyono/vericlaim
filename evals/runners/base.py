from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "dataset_path": str(self.dataset_path),
            "metrics": self.metrics,
            "cost_usd": self.cost_usd,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "n_samples": self.n_samples,
            "n_failures": self.n_failures,
            "prompt_hashes": self.prompt_hashes,
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
        }

    def save(self, path: Path) -> None:
        """Serialize this result to a JSON file for later comparison."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "SuiteResult":
        """Deserialize a previously saved SuiteResult."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            suite_name=data["suite_name"],
            dataset_path=Path(data["dataset_path"]),
            metrics=data.get("metrics", {}),
            cost_usd=data.get("cost_usd", 0.0),
            latency_p50_ms=int(data.get("latency_p50_ms", 0)),
            latency_p95_ms=int(data.get("latency_p95_ms", 0)),
            n_samples=int(data.get("n_samples", 0)),
            n_failures=int(data.get("n_failures", 0)),
            prompt_hashes=data.get("prompt_hashes", {}),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            notes=data.get("notes", ""),
        )
