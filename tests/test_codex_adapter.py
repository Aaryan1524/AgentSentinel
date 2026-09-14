import unittest

from agent_sentinel.adapters.codex import event_from_payload
from agent_sentinel.core.models import EventKind


class CodexAdapterTests(unittest.TestCase):
    def test_generic_notification_maps_to_completion(self) -> None:
        event = event_from_payload({"type": "agent-turn-complete", "thread_id": "thread-1"})

        self.assertEqual(event.kind, EventKind.AGENT_FINISHED)
        self.assertEqual(event.agent, "codex")
        self.assertEqual(event.metadata["thread_id"], "thread-1")

    def test_attention_and_rate_limit_text_are_not_claimed_as_completion(self) -> None:
        attention = event_from_payload({"message": "Permission approval required"})
        limited = event_from_payload({"message": "Rate limit reached"})

        self.assertEqual(attention.kind, EventKind.NEEDS_USER_ACTION)
        self.assertEqual(limited.kind, EventKind.RATE_LIMITED)
        self.assertEqual(limited.confidence.value, "unknown")
