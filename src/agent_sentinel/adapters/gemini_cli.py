"""Gemini CLI command-hook adapter."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from agent_sentinel.core.models import Confidence, Event, EventKind
from agent_sentinel.core.runtime import record_and_notify

AGENT_NAME = "gemini-cli"


def _event_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "gemini-hook-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metadata(payload: dict[str, Any]) -> dict[str, str]:
    metadata = {"hook_event": str(payload.get("hook_event_name", "unknown"))}
    for key in ("session_id", "cwd", "notification_type"):
        if payload.get(key) is not None:
            metadata[key] = str(payload[key])
    return metadata


def event_from_payload(payload: dict[str, Any]) -> Event | None:
    """Translate Gemini CLI lifecycle and notification hooks.

    Gemini CLI does not publish a quota-reset timestamp in its hook contract.
    A rate-limit-looking notification is useful as an immediate alert, but it
    remains an unknown-timing event.
    """
    hook_event = payload.get("hook_event_name")
    kind: EventKind | None = None
    message: str | None = None
    metadata = _metadata(payload)

    if hook_event == "AfterAgent":
        kind = EventKind.AGENT_FINISHED
        message = "Gemini CLI finished responding."
    elif hook_event == "Notification":
        notification_message = str(payload.get("message", ""))
        if "rate limit" in notification_message.lower():
            kind = EventKind.RATE_LIMITED
            message = "Gemini CLI is rate limited."
        else:
            kind = EventKind.NEEDS_USER_ACTION
            message = "Gemini CLI needs your attention."

    if kind is None:
        return None

    return Event.create(
        agent=AGENT_NAME,
        kind=kind,
        confidence=Confidence.UNKNOWN,
        message=message,
        metadata=metadata,
        event_id=_event_id(payload),
    )


def main() -> int:
    """Read one JSON hook payload and record it without altering Gemini flow."""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        event = event_from_payload(payload)
        if event is not None:
            record_and_notify(event)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
