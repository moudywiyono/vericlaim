from __future__ import annotations

from ingestion.models import ClaimPacket
from orchestration.nodes.base import Node, NodeResult
from orchestration.state import EvidenceStore


class ConsistencyAuditorNode(Node):
    """Stub — Phase 2/3 implementation pending."""

    @property
    def name(self) -> str:
        return "consistency_auditor"

    async def run(self, store: EvidenceStore, packet: ClaimPacket, degraded_context: dict[str, str] | None = None) -> NodeResult:
        return self._skipped_result(store)
