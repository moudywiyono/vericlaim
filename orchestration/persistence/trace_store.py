"""
Append-only JSONL trace store with optional Langfuse forwarding.

Every node execution appends a structured JSON line to
<claim_id>.jsonl in the configured trace directory.
If LANGFUSE_* env vars are set, events are also forwarded to Langfuse.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TRACE_DIR = Path(os.getenv("VERICLAIM_TRACE_DIR", "traces"))
_LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))


def _get_langfuse() -> Any:
    if not _LANGFUSE_ENABLED:
        return None
    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]
        return Langfuse()
    except Exception as e:
        logger.warning("Langfuse unavailable: %s", e)
        return None


class TraceStore:
    def __init__(self, trace_dir: Path | None = None) -> None:
        self._trace_dir = trace_dir or _TRACE_DIR
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        self._langfuse = _get_langfuse()

    def _claim_file(self, claim_id: str) -> Path:
        return self._trace_dir / f"{claim_id}.jsonl"

    def _append(self, claim_id: str, event: dict[str, Any]) -> None:
        line = json.dumps(event, default=str)
        with self._claim_file(claim_id).open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def record_node(
        self,
        claim_id: str,
        node_name: str,
        attempt: int,
        status: str,
        elapsed_ms: int,
        cost_usd: float,
        failure_type: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "event": "node_execution",
            "claim_id": claim_id,
            "node_name": node_name,
            "attempt": attempt,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "cost_usd": cost_usd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if failure_type:
            event["failure_type"] = failure_type
        if error:
            event["error"] = error
        if metadata:
            event["metadata"] = metadata

        self._append(claim_id, event)

        if self._langfuse:
            try:
                self._langfuse.trace(
                    id=claim_id,
                    name=f"node:{node_name}",
                    metadata=event,
                )
            except Exception as e:
                logger.debug("Langfuse record failed (non-fatal): %s", e)

    def record_claim(
        self,
        claim_id: str,
        state: str,
        claim_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "event": "claim_state_transition",
            "claim_id": claim_id,
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if claim_type:
            event["claim_type"] = claim_type
        if metadata:
            event["metadata"] = metadata

        self._append(claim_id, event)

    def read_trace(self, claim_id: str) -> list[dict[str, Any]]:
        """Return all trace events for a claim, in order."""
        path = self._claim_file(claim_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events
