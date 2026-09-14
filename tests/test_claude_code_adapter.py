import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from datetime import datetime, timedelta, timezone

from agent_sentinel.adapters.claude_code import AGENT_NAME, WINDOW_KEY, event_from_payload, main
from agent_sentinel.core.models import Confidence, EventKind
from agent_sentinel.core.store import EventStore, UsageWindow


class ClaudeCodeAdapterTests(unittest.TestCase):
    def test_stop_translates_to_a_completion_event(self) -> None:
        event = event_from_payload(
            {"hook_event_name": "Stop", "session_id": "session-1", "cwd": "/work"}
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, EventKind.AGENT_FINISHED)
        self.assertEqual(event.metadata["session_id"], "session-1")

    def test_rate_limit_stays_unknown_without_an_active_window(self) -> None:
        event = event_from_payload(
            {"hook_event_name": "StopFailure", "error": "rate_limit", "session_id": "session-1"}
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, EventKind.RATE_LIMITED)
        self.assertEqual(event.confidence.value, "unknown")
        self.assertIsNone(event.reset_at)

    def test_rate_limit_infers_reset_from_first_prompt_window(self) -> None:
        started = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
        event = event_from_payload(
            {"hook_event_name": "StopFailure", "error": "rate_limit", "session_id": "session-1"},
            usage_window=UsageWindow(
                agent=AGENT_NAME,
                window_key=WINDOW_KEY,
                started_at=started,
                reset_at=started + timedelta(hours=5),
            ),
            occurred_at=started + timedelta(hours=2),
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.confidence, Confidence.INFERRED)
        self.assertEqual(event.reset_at, started + timedelta(hours=5))
        self.assertEqual(event.metadata["window_duration_seconds"], 18_000)

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

    def test_prompt_then_rate_limit_uses_the_reset_queued_at_window_start(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = str(Path(directory) / "state.sqlite3")
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state_path}):
                with patch(
                    "agent_sentinel.adapters.claude_code.schedule_usage_window_reset",
                    return_value="claude-window-reset-1",
                ) as schedule_reset:
                    with patch("sys.stdin", io.StringIO('{"hook_event_name":"UserPromptSubmit"}')):
                        self.assertEqual(main(), 0)
                    payload = '{"hook_event_name":"StopFailure","error":"rate_limit"}'
                    with patch("sys.stdin", io.StringIO(payload)):
                        self.assertEqual(main(), 0)
                store = EventStore()
                limited = next(event for event in store.recent() if event.kind is EventKind.RATE_LIMITED)

        self.assertEqual(limited.confidence, Confidence.INFERRED)
        self.assertIsNotNone(limited.reset_at)
        self.assertTrue(limited.metadata["usage_window_reset_event_id"].startswith("claude-code-window-reset-"))
        schedule_reset.assert_called_once()
