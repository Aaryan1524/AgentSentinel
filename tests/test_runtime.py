from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_sentinel.core.models import Event
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
