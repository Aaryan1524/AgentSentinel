from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from agent_sentinel.channels.qstash import QStashChannel
from agent_sentinel.channels.telegram import TelegramChannel
from agent_sentinel.core.models import Confidence, Event, EventKind


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"messageId":"qstash-1"}'


class QStashChannelTests(unittest.TestCase):
    def test_schedule_posts_a_deduplicated_future_telegram_delivery(self) -> None:
        event = Event.create(
            agent="claude-code",
            kind=EventKind.RESET_AVAILABLE,
            occurred_at=datetime(2026, 9, 14, 17, tzinfo=timezone.utc),
            reset_at=datetime(2026, 9, 14, 17, tzinfo=timezone.utc),
            confidence=Confidence.INFERRED,
            event_id="window-reset-1",
        )
        channel = QStashChannel("qstash-token", TelegramChannel("telegram-token", "chat-1"))

        with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            channel.schedule(event)

        request = urlopen.call_args.args[0]
        self.assertIn("https%3A%2F%2Fapi.telegram.org%2Fbottelegram-token%2FsendMessage", request.full_url)
        self.assertEqual(request.get_header("Upstash-not-before"), "1789405200")
        self.assertEqual(request.get_header("Upstash-deduplication-id"), "window-reset-1")
        self.assertIn(b"chat_id=chat-1", request.data)
        self.assertIn(b"Reset%3A", request.data)
