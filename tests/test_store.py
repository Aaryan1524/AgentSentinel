from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timedelta, timezone

from agent_sentinel.core.models import Confidence, Event
from agent_sentinel.core.store import EventStore


class EventStoreTests(unittest.TestCase):
    def test_record_is_idempotent_and_returns_most_recent_first(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "state.sqlite3")
            earlier = Event.create(
                agent="gemini-cli",
                kind="agent_finished",
                occurred_at="2026-09-14T11:00:00Z",
                event_id="earlier",
            )
            later = Event.create(
                agent="claude-code",
                kind="rate_limited",
                occurred_at="2026-09-14T12:00:00Z",
                reset_at="2026-09-14T17:00:00Z",
                confidence=Confidence.CONFIRMED,
                event_id="later",
            )

            self.assertTrue(store.record(earlier))
            self.assertFalse(store.record(earlier))
            self.assertTrue(store.record(later))

            self.assertEqual([event.event_id for event in store.recent()], ["later", "earlier"])

    def test_recent_rejects_an_invalid_limit(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "at least 1"):
                EventStore(Path(directory) / "state.sqlite3").recent(0)

    def test_get_returns_a_stored_event_or_none(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "state.sqlite3")
            event = Event.create(agent="gemini-cli", kind="agent_finished", event_id="event-1")
            store.record(event)

            self.assertEqual(store.get("event-1"), event)
            self.assertIsNone(store.get("missing"))

    def test_usage_window_keeps_its_first_start_until_it_expires(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "state.sqlite3")
            started = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
            first = store.begin_usage_window(
                "claude-code", "account", started, timedelta(hours=5)
            )
            repeated = store.begin_usage_window(
                "claude-code", "account", started + timedelta(hours=1), timedelta(hours=5)
            )
            active = store.active_usage_window(
                "claude-code", "account", started + timedelta(hours=4)
            )
            expired = store.active_usage_window(
                "claude-code", "account", started + timedelta(hours=5)
            )

        self.assertEqual(first.started_at, started)
        self.assertEqual(first.reset_at, started + timedelta(hours=5))
        self.assertEqual(repeated, first)
        self.assertEqual(active, first)
        self.assertIsNone(expired)

    def test_schedule_accepts_a_utc_z_timestamp_on_all_supported_pythons(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "state.sqlite3")
            event = Event.create(agent="claude-code", kind="reset_available", event_id="reset-z")
            store.record(event)

            scheduled = store.schedule(event.event_id, "2026-09-14T17:00:00Z")

        self.assertEqual(scheduled.due_at.isoformat(), "2026-09-14T17:00:00+00:00")
