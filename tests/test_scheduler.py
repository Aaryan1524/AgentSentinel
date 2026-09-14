from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_sentinel.core.models import Event
from agent_sentinel.core.scheduler import LocalScheduler
from agent_sentinel.core.store import EventStore


class LocalSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)

    def test_due_event_is_delivered_once_and_recorded(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "state.sqlite3")
            event = Event.create(agent="claude-code", kind="reset_available", event_id="reset-1")
            store.record(event)
            store.schedule(event.event_id, self.now - timedelta(minutes=1))
            delivered = []

            results = LocalScheduler(store, delivered.append).run_due(self.now)

            self.assertEqual([result.outcome for result in results], ["delivered"])
            self.assertEqual(delivered, [event])
            record = store.scheduled(event.event_id)
            assert record is not None
            self.assertEqual(record.status, "delivered")
            self.assertEqual(record.attempt_count, 1)
            self.assertEqual(LocalScheduler(store, delivered.append).run_due(self.now), [])

    def test_failed_delivery_stays_pending_for_retry(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "state.sqlite3")
            event = Event.create(agent="gemini-cli", kind="agent_finished", event_id="finish-1")
            store.record(event)
            store.schedule(event.event_id, self.now)

            results = LocalScheduler(store, lambda _event: (_ for _ in ()).throw(RuntimeError("offline"))).run_due(self.now)

            self.assertEqual(results[0].outcome, "failed")
            record = store.scheduled(event.event_id)
            assert record is not None
            self.assertEqual(record.status, "pending")
            self.assertEqual(record.attempt_count, 1)
            self.assertEqual(record.last_error, "offline")

    def test_dry_run_does_not_claim_or_modify_due_event(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "state.sqlite3")
            event = Event.create(agent="gemini-cli", kind="agent_finished", event_id="finish-2")
            store.record(event)
            store.schedule(event.event_id, self.now)

            results = LocalScheduler(store, lambda _event: self.fail("must not send")).run_due(self.now, dry_run=True)

            self.assertEqual(results[0].outcome, "would_deliver")
            record = store.scheduled(event.event_id)
            assert record is not None
            self.assertEqual(record.status, "pending")
            self.assertEqual(record.attempt_count, 0)
