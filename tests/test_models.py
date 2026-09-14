from datetime import datetime, timezone
import unittest

from agent_sentinel.core.models import Confidence, Event, EventKind


class EventTests(unittest.TestCase):
    def test_round_trip_preserves_a_confirmed_reset(self) -> None:
        event = Event.create(
            agent="claude-code",
            kind=EventKind.RATE_LIMITED,
            occurred_at="2026-09-14T12:00:00Z",
            reset_at="2026-09-14T17:00:00Z",
            confidence=Confidence.CONFIRMED,
            event_id="source-event-1",
            metadata={"provider": "anthropic"},
        )

        restored = Event.from_dict(event.to_dict())

        self.assertEqual(restored, event)
        self.assertEqual(restored.reset_at, datetime(2026, 9, 14, 17, tzinfo=timezone.utc))

    def test_inferred_or_confirmed_requires_a_reset_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires reset_at"):
            Event.create(
                agent="gemini-cli",
                kind=EventKind.RATE_LIMITED,
                confidence=Confidence.INFERRED,
            )

    def test_unknown_confidence_cannot_claim_a_reset_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires confirmed or inferred"):
            Event.create(
                agent="gemini-cli",
                kind=EventKind.RATE_LIMITED,
                reset_at="2026-09-14T17:00:00Z",
            )
