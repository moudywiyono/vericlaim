"""
SQLite-backed claim state store.

Persists ClaimRecord rows with full transition history.
Each upsert appends a transition row; the current state is always the latest.
Migration path to Postgres: swap sqlite3 for psycopg2 + adjust DDL.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from orchestration.state import ClaimRecord, ClaimState

_DB_PATH = os.getenv("VERICLAIM_DB_PATH", "vericlaim.db")

_DDL = """
CREATE TABLE IF NOT EXISTS claim_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    state TEXT NOT NULL,
    claim_type TEXT,
    routing_confidence REAL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claim_state_claim_id ON claim_state(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_state_state ON claim_state(state);
"""


class ClaimStateStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or _DB_PATH)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_DDL)

    def upsert(self, record: ClaimRecord) -> None:
        """Insert a new row for every state transition (full history)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO claim_state
                    (claim_id, state, claim_type, routing_confidence,
                     error_message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.claim_id,
                    record.state.value,
                    record.claim_type,
                    record.routing_confidence,
                    record.error_message,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )

    def get_current(self, claim_id: str) -> ClaimRecord | None:
        """Return the most recent state row for a claim."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM claim_state
                WHERE claim_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (claim_id,),
            ).fetchone()
        if row is None:
            return None
        return ClaimRecord(
            claim_id=row["claim_id"],
            state=ClaimState(row["state"]),
            claim_type=row["claim_type"],
            routing_confidence=row["routing_confidence"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_by_state(self, state: ClaimState) -> list[str]:
        """Return claim_ids currently in the given state (useful for crash recovery)."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT claim_id FROM claim_state cs1
                WHERE state = ?
                  AND id = (
                      SELECT MAX(id) FROM claim_state cs2
                      WHERE cs2.claim_id = cs1.claim_id
                  )
                """,
                (state.value,),
            ).fetchall()
        return [r["claim_id"] for r in rows]

    def count_by_state(self) -> dict[str, int]:
        """Counts per current state — for ops dashboards."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT state, COUNT(*) as cnt FROM claim_state cs1
                WHERE id = (
                    SELECT MAX(id) FROM claim_state cs2
                    WHERE cs2.claim_id = cs1.claim_id
                )
                GROUP BY state
                """
            ).fetchall()
        return {r["state"]: r["cnt"] for r in rows}
