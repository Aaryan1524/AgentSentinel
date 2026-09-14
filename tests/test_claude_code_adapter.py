import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_sentinel.adapters.claude_code import event_from_payload, main
from agent_sentinel.core.models import EventKind
from agent_sentinel.core.store import EventStore


class ClaudeCodeAdapterTests(unittest.TestCase):
    def test_stop_translates_to_a_completion_event(self) -> None:
        event = event_from_payload(
            {"hook_event_name": "Stop", "session_id": "session-1", "cwd": "/work"}
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, EventKind.AGENT_FINISHED)
        self.assertEqual(event.metadata["session_id"], "session-1")

    def test_rate_limit_stays_unknown_without_a_documented_reset_time(self) -> None:
        event = event_from_payload(
            {"hook_event_name": "StopFailure", "error": "rate_limit", "session_id": "session-1"}
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, EventKind.RATE_LIMITED)
        self.assertEqual(event.confidence.value, "unknown")
        self.assertIsNone(event.reset_at)

    def test_unrelated_stop_failure_is_ignored(self) -> None:
        self.assertIsNone(
            event_from_payload({"hook_event_name": "StopFailure", "error": "server_error"})
        )

    def test_command_hook_records_and_deduplicates(self) -> None:
        payload = '{"hook_event_name":"Stop","session_id":"session-1"}'
        with TemporaryDirectory() as directory:
            state_path = str(Path(directory) / "state.sqlite3")
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state_path}):
                with patch("sys.stdin", io.StringIO(payload)):
                    self.assertEqual(main(), 0)
                with patch("sys.stdin", io.StringIO(payload)):
                    self.assertEqual(main(), 0)
                events = EventStore().recent()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, EventKind.AGENT_FINISHED)
