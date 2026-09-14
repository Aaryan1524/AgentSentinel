import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from agent_sentinel.adapters.codex import event_from_payload, run_main
from agent_sentinel.core.models import Confidence, EventKind
from agent_sentinel.core.store import EventStore, UsageWindow


class CodexAdapterTests(unittest.TestCase):
    def test_generic_notification_maps_to_completion(self) -> None:
        event = event_from_payload({"type": "agent-turn-complete", "thread_id": "thread-1"})

        self.assertEqual(event.kind, EventKind.AGENT_FINISHED)
        self.assertEqual(event.agent, "codex")
        self.assertEqual(event.metadata["thread_id"], "thread-1")

    def test_attention_and_rate_limit_text_are_not_claimed_as_completion(self) -> None:
        attention = event_from_payload({"message": "Permission approval required"})
        window = UsageWindow(
            agent="codex",
            window_key="account",
            started_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            reset_at=datetime(2026, 9, 14, 17, tzinfo=timezone.utc),
        )
        limited = event_from_payload({"message": "Rate limit reached"}, usage_window=window)

        self.assertEqual(attention.kind, EventKind.NEEDS_USER_ACTION)
        self.assertEqual(limited.kind, EventKind.RATE_LIMITED)
        self.assertEqual(limited.confidence, Confidence.INFERRED)
        self.assertEqual(limited.reset_at, window.reset_at)

    def test_launcher_starts_the_window_before_running_codex(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = str(Path(directory) / "state.sqlite3")
            completed = Mock(returncode=7)
            with patch.dict(os.environ, {"AGENT_SENTINEL_STATE": state_path}), patch(
                "agent_sentinel.adapters.codex.schedule_usage_window_reset"
            ) as schedule_reset, patch(
                "agent_sentinel.adapters.codex.subprocess.run", return_value=completed
            ) as run, patch("sys.argv", ["sentinel-codex", "resume"]):
                self.assertEqual(run_main(), 7)
                active = EventStore().active_usage_window(
                    "codex", "account", datetime.now(timezone.utc)
                )

        self.assertIsNotNone(active)
        schedule_reset.assert_called_once()
        run.assert_called_once_with(["codex", "resume"], check=False)
