"""
Supabase-backed claim state store.

One row per claim in the `claim_states` table — state is overwritten on each
transition. Uses the Supabase REST client (service_role key) so no direct
Postgres password is needed.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from supabase import create_client, Client

from orchestration.state import ClaimRecord, ClaimState

_TABLE = "claim_states"


def _client() -> Client:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    return create_client(url, key)


class ClaimStateStore:
    def __init__(self) -> None:
        self._db = _client()

    def upsert(self, record: ClaimRecord) -> None:
        """Insert or update the current state for a claim."""
        self._db.table(_TABLE).upsert({
            "claim_id":   record.claim_id,
            "state":      record.state.value,
            "claim_type": record.claim_type,
            "confidence": record.routing_confidence,
            "specialist_status": {},
            "updated_at": record.updated_at.isoformat(),
        }).execute()

    def get_current(self, claim_id: str) -> ClaimRecord | None:
        """Return the current state row for a claim."""
        res = (
            self._db.table(_TABLE)
            .select("*")
            .eq("claim_id", claim_id)
            .limit(1)
            .execute()
        )
        if not res or not res.data:
            return None
        row = res.data[0]
        return ClaimRecord(
            claim_id=row["claim_id"],
            state=ClaimState(row["state"]),
            claim_type=row["claim_type"],
            routing_confidence=row["confidence"],
            error_message=None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_by_state(self, state: ClaimState) -> list[str]:
        """Return all claim_ids currently in the given state."""
        res = (
            self._db.table(_TABLE)
            .select("claim_id")
            .eq("state", state.value)
            .execute()
        )
        return [r["claim_id"] for r in (res.data or [])]

    def list_by_states(self, states: list[ClaimState]) -> list[ClaimRecord]:
        """Return all ClaimRecords currently in any of the given states."""
        values = [s.value for s in states]
        res = (
            self._db.table(_TABLE)
            .select("*")
            .in_("state", values)
            .execute()
        )
        records = []
        for row in (res.data if res and res.data else []):
            records.append(ClaimRecord(
                claim_id=row["claim_id"],
                state=ClaimState(row["state"]),
                claim_type=row["claim_type"],
                routing_confidence=row["confidence"],
                error_message=None,
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            ))
        return records

    def count_by_state(self) -> dict[str, int]:
        """Count of claims per state — for ops dashboards."""
        res = self._db.table(_TABLE).select("state").execute()
        counts: dict[str, int] = {}
        for row in (res.data or []):
            counts[row["state"]] = counts.get(row["state"], 0) + 1
        return counts
