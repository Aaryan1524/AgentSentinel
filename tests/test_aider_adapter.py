import unittest

from agent_sentinel.adapters.aider import event
from agent_sentinel.core.models import EventKind


class AiderAdapterTests(unittest.TestCase):
    def test_notification_bridge_records_attention_required(self) -> None:
        result = event()

        self.assertEqual(result.agent, "aider")
        self.assertEqual(result.kind, EventKind.NEEDS_USER_ACTION)
        self.assertEqual(result.confidence.value, "unknown")
