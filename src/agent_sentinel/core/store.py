"""Small, durable local event store with idempotent writes."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .models import Event


def default_state_path() -> Path:
    configured = os.environ.get("AGENT_SENTINEL_STATE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".agent-sentinel" / "state.sqlite3"


class EventStore:
    """SQLite-backed event storage that survives a hook process exiting."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_state_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    agent TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    reset_at TEXT,
                    confidence TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS events_recent ON events (occurred_at DESC)"
            )
            connection.commit()
        finally:
            connection.close()

    def record(self, event: Event) -> bool:
        """Persist an event. Returns False when the id was already recorded."""
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO events
                  (event_id, agent, kind, occurred_at, reset_at, confidence, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.agent,
                    event.kind.value,
                    event.occurred_at.isoformat(),
                    event.reset_at.isoformat() if event.reset_at else None,
                    event.confidence.value,
                    json.dumps(event.to_dict(), sort_keys=True),
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def recent(self, limit: int = 20) -> list[Event]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT payload FROM events ORDER BY occurred_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            connection.close()
        return [Event.from_dict(json.loads(row["payload"])) for row in rows]

    def get(self, event_id: str) -> Event | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
        finally:
            connection.close()
        return Event.from_dict(json.loads(row["payload"])) if row else None
