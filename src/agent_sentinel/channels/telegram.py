"""Telegram Bot API delivery without external Python dependencies."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from agent_sentinel.core.models import Event


class TelegramChannel:
    """Send plain-text Agent Sentinel notifications through a Telegram bot."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        if not bot_token or not chat_id:
            raise ValueError("Telegram bot token and chat ID are required")
        self.bot_token = bot_token
        self.chat_id = chat_id

    @classmethod
    def from_environment(cls) -> "TelegramChannel":
        return cls(
            os.environ.get("AGENT_SENTINEL_TELEGRAM_BOT_TOKEN", ""),
            os.environ.get("AGENT_SENTINEL_TELEGRAM_CHAT_ID", ""),
        )

    @staticmethod
    def render(event: Event) -> str:
        lines = ["Agent Sentinel", f"{event.agent}: {event.kind.value.replace('_', ' ')}"]
        if event.message:
            lines.append(event.message)
        if event.reset_at:
            lines.append(f"Reset: {event.reset_at.isoformat()} ({event.confidence.value})")
        elif event.kind.value == "rate_limited":
            lines.append("Reset time: unknown")
        return "\n".join(lines)

    def send(self, event: Event) -> None:
        body = urllib.parse.urlencode({"chat_id": self.chat_id, "text": self.render(event)}).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=body,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Telegram delivery failed: {error}") from error
        if not payload.get("ok"):
            raise RuntimeError("Telegram delivery failed: API response was not ok")
