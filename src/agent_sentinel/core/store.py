"""Small, durable local event store with idempotent writes."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Event


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    event_id: str
    due_at: datetime
    status: str
    attempt_count: int
    delivered_at: datetime | None
    last_error: str | None


def _parse_timestamp(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("scheduled timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_events (
                    event_id TEXT PRIMARY KEY REFERENCES events(event_id),
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    delivered_at TEXT,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS scheduled_events_due "
                "ON scheduled_events (status, due_at)"
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

    def schedule(self, event_id: str, due_at: datetime | str) -> ScheduledEvent:
        if self.get(event_id) is None:
            raise ValueError(f"event not found: {event_id}")
        due = _parse_timestamp(due_at)
        now = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO scheduled_events
                    (event_id, due_at, status, attempt_count, delivered_at, last_error, updated_at)
                VALUES (?, ?, 'pending', 0, NULL, NULL, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    due_at = excluded.due_at,
                    status = 'pending',
                    attempt_count = 0,
                    delivered_at = NULL,
                    last_error = NULL,
                    updated_at = excluded.updated_at
                """,
                (event_id, due.isoformat(), now),
            )
            connection.commit()
        finally:
            connection.close()
        scheduled = self.scheduled(event_id)
        if scheduled is None:
            raise RuntimeError("scheduled event was not persisted")
        return scheduled

    def scheduled(self, event_id: str) -> ScheduledEvent | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM scheduled_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        finally:
            connection.close()
        return self._scheduled_from_row(row) if row else None

    def schedules(self, limit: int = 20) -> list[ScheduledEvent]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM scheduled_events ORDER BY due_at DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            connection.close()
        return [self._scheduled_from_row(row) for row in rows]

    def due(self, now: datetime, stale_after: timedelta = timedelta(minutes=5)) -> list[ScheduledEvent]:
        current = _parse_timestamp(now)
        stale_before = (current - stale_after).isoformat()
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM scheduled_events
                WHERE due_at <= ? AND (status = 'pending' OR (status = 'processing' AND updated_at <= ?))
                ORDER BY due_at ASC
                """,
                (current.isoformat(), stale_before),
            ).fetchall()
        finally:
            connection.close()
        return [self._scheduled_from_row(row) for row in rows]

    def claim(self, event_id: str, now: datetime, stale_after: timedelta = timedelta(minutes=5)) -> bool:
        current = _parse_timestamp(now)
        stale_before = (current - stale_after).isoformat()
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE scheduled_events SET status = 'processing', updated_at = ?
                WHERE event_id = ? AND (status = 'pending' OR (status = 'processing' AND updated_at <= ?))
                """,
                (current.isoformat(), event_id, stale_before),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def mark_delivered(self, event_id: str, now: datetime) -> None:
        self._finish(event_id, now, "delivered", None)

    def mark_failed(self, event_id: str, now: datetime, error: str) -> None:
        self._finish(event_id, now, "pending", error[:500])

    def _finish(self, event_id: str, now: datetime, status: str, error: str | None) -> None:
        current = _parse_timestamp(now).isoformat()
        delivered_at = current if status == "delivered" else None
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE scheduled_events
                SET status = ?, attempt_count = attempt_count + 1, delivered_at = ?, last_error = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (status, delivered_at, error, current, event_id),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _scheduled_from_row(row: sqlite3.Row) -> ScheduledEvent:
        return ScheduledEvent(
            event_id=row["event_id"],
            due_at=_parse_timestamp(row["due_at"]),
            status=row["status"],
            attempt_count=row["attempt_count"],
            delivered_at=_parse_timestamp(row["delivered_at"]) if row["delivered_at"] else None,
            last_error=row["last_error"],
        )
