"""Telegram Bot API delivery without external Python dependencies."""

from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

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
        secrets_path = Path(
            os.environ.get("AGENT_SENTINEL_SECRETS", "~/.agent-sentinel/secrets.env")
        ).expanduser()
        if secrets_path.exists():
            if os.name == "posix" and secrets_path.stat().st_uid == os.geteuid():
                mode = stat.S_IMODE(secrets_path.stat().st_mode)
                if mode & (stat.S_IRWXG | stat.S_IRWXO):
                    os.chmod(secrets_path, 0o600)
            for line in secrets_path.read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() in {
                    "AGENT_SENTINEL_TELEGRAM_BOT_TOKEN",
                    "AGENT_SENTINEL_TELEGRAM_CHAT_ID",
                    "AGENT_SENTINEL_QSTASH_TOKEN",
                    "AGENT_SENTINEL_QSTASH_DESTINATION",
                }:
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
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
