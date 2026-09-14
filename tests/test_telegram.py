from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from agent_sentinel.channels.telegram import TelegramChannel
from agent_sentinel.core.models import Confidence, Event


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok": true}'


class TelegramChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = Event.create(
            agent="claude-code",
            kind="rate_limited",
            occurred_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            reset_at=datetime(2026, 9, 14, 17, tzinfo=timezone.utc),
            confidence=Confidence.CONFIRMED,
            event_id="limit-1",
        )

    def test_render_includes_reset_confidence(self) -> None:
        rendered = TelegramChannel("token", "chat").render(self.event)

        self.assertIn("claude-code: rate limited", rendered)
        self.assertIn("confirmed", rendered)

    def test_send_posts_plain_text_to_telegram(self) -> None:
        with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            TelegramChannel("token", "chat").send(self.event)

        request = urlopen.call_args.args[0]
        self.assertIn("bottoken/sendMessage", request.full_url)
        self.assertIn(b"chat_id=chat", request.data)

    def test_from_environment_loads_the_local_secret_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "secrets.env"
            path.write_text("AGENT_SENTINEL_TELEGRAM_BOT_TOKEN=file-token\nAGENT_SENTINEL_TELEGRAM_CHAT_ID=file-chat\n")
            with patch.dict("os.environ", {"AGENT_SENTINEL_SECRETS": str(path)}, clear=True):
                channel = TelegramChannel.from_environment()

        self.assertEqual(channel.bot_token, "file-token")
        self.assertEqual(channel.chat_id, "file-chat")
