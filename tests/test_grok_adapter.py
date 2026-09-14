import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from agent_sentinel.adapters.grok import event_from_payload, main
from agent_sentinel.core.models import Confidence, EventKind
from agent_sentinel.core.store import EventStore, UsageWindow


class GrokAdapterTests(unittest.TestCase):
    def test_stop_and_idle_notification_map_to_completion(self) -> None:
        stop = event_from_payload({"hook_event_name": "Stop", "session_id": "session-1"})
        idle = event_from_payload({"hook_event_name": "Notification", "notificationType": "idle_prompt"})

        self.assertEqual(stop.kind, EventKind.AGENT_FINISHED)
        self.assertEqual(idle.kind, EventKind.AGENT_FINISHED)

    def test_rate_limit_and_permission_notifications_are_actionable(self) -> None:
        window = UsageWindow(
            agent="grok",
            window_key="account",
            started_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            reset_at=datetime(2026, 9, 14, 17, tzinfo=timezone.utc),
        )
        limited = event_from_payload(
            {"hook_event_name": "StopFailure", "error": "rate_limit"}, usage_window=window
        )
        permission = event_from_payload(
            {"hook_event_name": "Notification", "notificationType": "permission_prompt"}
        )

        self.assertEqual(limited.kind, EventKind.RATE_LIMITED)
        self.assertEqual(limited.confidence, Confidence.INFERRED)
        self.assertEqual(limited.reset_at, window.reset_at)
        self.assertEqual(permission.kind, EventKind.NEEDS_USER_ACTION)

    def test_user_prompt_starts_and_queues_one_usage_window(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = str(Path(directory) / "state.sqlite3")
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state_path}):
                with patch(
                    "agent_sentinel.adapters.grok.schedule_usage_window_reset"
                ) as schedule_reset, patch(
                    "sys.stdin", io.StringIO('{"hook_event_name":"UserPromptSubmit"}')
                ):
                    self.assertEqual(main(), 0)
                active = EventStore().active_usage_window(
                    "grok", "account", datetime.now(timezone.utc)
                )

        self.assertIsNotNone(active)
        schedule_reset.assert_called_once()
