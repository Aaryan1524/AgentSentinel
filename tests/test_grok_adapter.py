import unittest

from agent_sentinel.adapters.grok import event_from_payload
from agent_sentinel.core.models import EventKind


class GrokAdapterTests(unittest.TestCase):
    def test_stop_and_idle_notification_map_to_completion(self) -> None:
        stop = event_from_payload({"hook_event_name": "Stop", "session_id": "session-1"})
        idle = event_from_payload({"hook_event_name": "Notification", "notificationType": "idle_prompt"})

        self.assertEqual(stop.kind, EventKind.AGENT_FINISHED)
        self.assertEqual(idle.kind, EventKind.AGENT_FINISHED)

    def test_rate_limit_and_permission_notifications_are_actionable(self) -> None:
        limited = event_from_payload({"hook_event_name": "StopFailure", "error": "rate_limit"})
        permission = event_from_payload(
            {"hook_event_name": "Notification", "notificationType": "permission_prompt"}
        )

        self.assertEqual(limited.kind, EventKind.RATE_LIMITED)
        self.assertEqual(limited.confidence.value, "unknown")
        self.assertEqual(permission.kind, EventKind.NEEDS_USER_ACTION)
