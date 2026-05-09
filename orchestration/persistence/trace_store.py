"""
Append-only JSONL trace store with Langfuse v2 forwarding.

Every node execution appends a structured JSON line to
<claim_id>.jsonl in the configured trace directory.

Langfuse integration (v2 SDK, compatible with Langfuse Cloud):
  - One trace per claim (claim_id used as trace ID)
  - One span per node_execution event
  - One generation span per llm_generation event
  - Langfuse is initialised lazily on first use so dotenv has time to load

Required env vars (leave blank to disable Langfuse):
  LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
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


def _make_langfuse() -> Any:
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return None
    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]
        client = Langfuse()
        host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        logger.info("Langfuse v2 client initialised (host=%s)", host)
        return client
    except Exception as e:
        logger.warning("Langfuse unavailable: %s", e)
        return None


class TraceStore:
    def __init__(self, trace_dir: Path | None = None) -> None:
        self._trace_dir = trace_dir or _TRACE_DIR
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        self._lf: Any = None
        self._lf_checked = False
        self._lf_traces: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Langfuse lazy helpers
    # ------------------------------------------------------------------

    def _client(self) -> Any:
        if not self._lf_checked:
            self._lf = _make_langfuse()
            self._lf_checked = True
        return self._lf

    def _trace(self, claim_id: str, claim_type: str | None = None) -> Any:
        lf = self._client()
        if lf is None:
            return None
        if claim_id not in self._lf_traces:
            try:
                self._lf_traces[claim_id] = lf.trace(
                    id=claim_id,
                    name="claim_pipeline",
                    metadata={"claim_type": claim_type or "unknown"},
                )
            except Exception as e:
                logger.debug("Langfuse trace create failed: %s", e)
                return None
        return self._lf_traces.get(claim_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _claim_file(self, claim_id: str) -> Path:
        return self._trace_dir / f"{claim_id}.jsonl"

    def _append(self, claim_id: str, event: dict[str, Any]) -> None:
        line = json.dumps(event, default=str)
        with self._claim_file(claim_id).open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------------
    # Public recording API
    # ------------------------------------------------------------------

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
        model_used: str | None = None,
        prompt_hash: str | None = None,
        claim_type: str | None = None,
        severity_bucket: str | None = None,
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
        if model_used:
            event["model_used"] = model_used
        if prompt_hash:
            event["prompt_hash"] = prompt_hash
        if claim_type:
            event["claim_type"] = claim_type
        if severity_bucket:
            event["severity_bucket"] = severity_bucket
        if metadata:
            event["metadata"] = metadata

        self._append(claim_id, event)

        trace = self._trace(claim_id, claim_type)
        if trace:
            try:
                trace.span(
                    name=f"node:{node_name}",
                    input={"node": node_name, "attempt": attempt},
                    output={"status": status, "cost_usd": cost_usd, "elapsed_ms": elapsed_ms},
                    metadata={
                        k: v for k, v in event.items()
                        if k not in ("event", "claim_id", "timestamp")
                    },
                )
            except Exception as e:
                logger.debug("Langfuse span failed (non-fatal): %s", e)

    def record_generation(
        self,
        claim_id: str,
        node_name: str,
        model: str,
        prompt_hash: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        claim_type: str | None = None,
        severity_bucket: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single LLM generation call within a node."""
        event: dict[str, Any] = {
            "event": "llm_generation",
            "claim_id": claim_id,
            "node_name": node_name,
            "model": model,
            "prompt_hash": prompt_hash,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if claim_type:
            event["claim_type"] = claim_type
        if severity_bucket:
            event["severity_bucket"] = severity_bucket
        if metadata:
            event["metadata"] = metadata

        self._append(claim_id, event)

        trace = self._trace(claim_id, claim_type)
        if trace:
            try:
                trace.generation(
                    name=f"gen:{node_name}",
                    model=model,
                    usage={"input": input_tokens, "output": output_tokens},
                    input={"prompt_hash": prompt_hash},
                    output={"cost_usd": cost_usd},
                    metadata={
                        "prompt_hash": prompt_hash,
                        "cost_usd": cost_usd,
                        "claim_type": claim_type,
                        "severity_bucket": severity_bucket,
                        **(metadata or {}),
                    },
                )
            except Exception as e:
                logger.debug("Langfuse generation failed (non-fatal): %s", e)

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
