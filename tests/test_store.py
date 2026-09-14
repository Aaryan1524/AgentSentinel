from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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
