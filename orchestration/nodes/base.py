from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ingestion.models import ClaimPacket
from orchestration.state import AgentStatus, EvidenceStore


@dataclass
class NodeResult:
    store: EvidenceStore
    status: AgentStatus
    cost_usd: float = 0.0
    latency_ms: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


class Node(ABC):
    """
    Abstract base for all specialist nodes.

    Each node receives the current EvidenceStore and the ClaimPacket (for raw assets),
    and returns a NodeResult containing an updated EvidenceStore. The orchestrator
    merges the result back into the shared store.

    Nodes must NOT:
    - Retry internally (retry is the orchestrator's responsibility)
    - Access the EvidenceStore of other parallel nodes
    - Write to any shared mutable state
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique node identifier — must match the key in orchestration/graph.py."""

    @property
    def timeout_s(self) -> float:
        """Per-node timeout in seconds. Override per specialist as needed."""
        return 30.0

    @abstractmethod
    async def run(
        self,
        store: EvidenceStore,
        packet: ClaimPacket,
        degraded_context: dict[str, str] | None = None,
    ) -> NodeResult:
        """
        Execute specialist logic. Return a NodeResult whose store contains only
        the findings this node produced (plus the agent status for self.name).
        The orchestrator handles merging into the shared EvidenceStore.

        degraded_context: per-agent amendment strings from upstream failures,
        produced by orchestration.failure.degradation.get_degraded_context().
        Nodes that make LLM calls should prepend relevant entries to their prompts.
        """

    def _skipped_result(self, store: EvidenceStore) -> NodeResult:
        return NodeResult(
            store=store.mark_agent(self.name, AgentStatus.SKIPPED),
            status=AgentStatus.SKIPPED,
        )
