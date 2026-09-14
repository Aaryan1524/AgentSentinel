"""One-time, off-device reset delivery through a user's Upstash QStash account."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from agent_sentinel.core.models import Event

from .telegram import TelegramChannel


class QStashChannel:
    """Schedule a Telegram message that survives the originating computer."""

    def __init__(self, token: str, telegram: TelegramChannel, destination: str | None = None) -> None:
        if not token:
            raise ValueError("QStash token is required")
        self.token = token
        self.telegram = telegram
        self.destination = destination or f"https://api.telegram.org/bot{telegram.bot_token}/sendMessage"

    @classmethod
    def from_environment(cls) -> "QStashChannel":
        telegram = TelegramChannel.from_environment()
        return cls(
            os.environ.get("AGENT_SENTINEL_QSTASH_TOKEN", ""),
            telegram,
            os.environ.get("AGENT_SENTINEL_QSTASH_DESTINATION") or None,
        )

    def schedule(self, event: Event) -> None:
        if event.reset_at is None:
            raise ValueError("a reset event needs a reset timestamp")
        destination = urllib.parse.quote(self.destination, safe="")
        body = urllib.parse.urlencode(
            {"chat_id": self.telegram.chat_id, "text": TelegramChannel.render(event)}
        ).encode()
        request = urllib.request.Request(
            f"https://qstash.upstash.io/v2/publish/{destination}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Upstash-Method": "POST",
                "Upstash-Not-Before": str(int(event.reset_at.timestamp())),
                "Upstash-Retries": "3",
                "Upstash-Deduplication-Id": event.event_id,
                "Upstash-Redact-Fields": "body,headers",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f"QStash scheduling failed: {error}") from error
        if not payload.get("messageId") and not payload.get("deduplicated"):
            raise RuntimeError("QStash scheduling failed: API response was invalid")
