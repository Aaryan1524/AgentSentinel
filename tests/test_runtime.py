from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_sentinel.core.models import Confidence, Event, EventKind
from agent_sentinel.core.runtime import record_and_notify
from agent_sentinel.core.store import EventStore


class RuntimeTests(unittest.TestCase):
    def test_records_then_sends_once_when_channel_is_configured(self) -> None:
        with TemporaryDirectory() as directory:
            event = Event.create(agent="codex", kind="agent_finished", event_id="codex-1")
            store = EventStore(Path(directory) / "state.sqlite3")
            channel = unittest.mock.Mock()
            with patch("agent_sentinel.core.runtime.TelegramChannel.from_environment", return_value=channel):
                self.assertTrue(record_and_notify(event, store))
                self.assertFalse(record_and_notify(event, store))

        channel.send.assert_called_once_with(event)

    def test_delivery_failure_never_discards_the_event(self) -> None:
        with TemporaryDirectory() as directory:
            event = Event.create(agent="grok", kind="rate_limited", event_id="grok-1")
            store = EventStore(Path(directory) / "state.sqlite3")
            channel = unittest.mock.Mock()
            channel.send.side_effect = RuntimeError("offline")
            with patch("agent_sentinel.core.runtime.TelegramChannel.from_environment", return_value=channel):
                self.assertTrue(record_and_notify(event, store))

            self.assertEqual(store.get(event.event_id), event)

    def test_timed_rate_limit_schedules_a_follow_up_reset_notification(self) -> None:
        with TemporaryDirectory() as directory:
            event = Event.create(
                agent="claude-code",
                kind=EventKind.RATE_LIMITED,
                occurred_at="2026-09-14T12:00:00Z",
                reset_at="2026-09-14T17:00:00Z",
                confidence=Confidence.INFERRED,
                event_id="claude-limit-1",
            )
            store = EventStore(Path(directory) / "state.sqlite3")
            channel = unittest.mock.Mock()
            with patch("agent_sentinel.core.runtime.TelegramChannel.from_environment", return_value=channel):
                self.assertTrue(record_and_notify(event, store))

            reset_event = store.get("claude-limit-1-reset-available")
            scheduled = store.scheduled("claude-limit-1-reset-available")

        self.assertIsNotNone(reset_event)
        assert reset_event is not None
        self.assertEqual(reset_event.kind, EventKind.RESET_AVAILABLE)
        self.assertEqual(reset_event.confidence, Confidence.INFERRED)
        self.assertEqual(reset_event.reset_at.isoformat(), "2026-09-14T17:00:00+00:00")
        self.assertIsNotNone(scheduled)
        assert scheduled is not None
        self.assertEqual(scheduled.due_at.isoformat(), "2026-09-14T17:00:00+00:00")
        channel.send.assert_called_once_with(event)
