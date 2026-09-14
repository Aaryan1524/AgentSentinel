import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_sentinel.adapters.gemini_cli import event_from_payload, main
from agent_sentinel.core.models import EventKind
from agent_sentinel.core.store import EventStore


class GeminiCliAdapterTests(unittest.TestCase):
    def test_after_agent_translates_to_completion(self) -> None:
        event = event_from_payload(
            {"hook_event_name": "AfterAgent", "session_id": "session-1", "timestamp": "2026-09-14T12:00:00Z"}
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, EventKind.AGENT_FINISHED)

    def test_permission_notification_needs_attention(self) -> None:
        event = event_from_payload(
            {
                "hook_event_name": "Notification",
                "notification_type": "ToolPermission",
                "message": "Permission needed for run_shell_command",
            }
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, EventKind.NEEDS_USER_ACTION)
        self.assertEqual(event.metadata["notification_type"], "ToolPermission")

    def test_rate_limit_notification_has_unknown_reset_time(self) -> None:
        event = event_from_payload(
            {"hook_event_name": "Notification", "message": "Rate limit reached"}
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, EventKind.RATE_LIMITED)
        self.assertEqual(event.confidence.value, "unknown")
        self.assertIsNone(event.reset_at)

    def test_command_hook_records_an_event(self) -> None:
        payload = '{"hook_event_name":"AfterAgent","session_id":"session-1"}'
        with TemporaryDirectory() as directory:
            state_path = str(Path(directory) / "state.sqlite3")
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state_path}):
                with patch("sys.stdin", io.StringIO(payload)):
                    self.assertEqual(main(), 0)
                events = EventStore().recent()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, EventKind.AGENT_FINISHED)
