"""Gemini CLI command-hook adapter."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_sentinel.core.models import Confidence, Event, EventKind
from agent_sentinel.core.runtime import (
    record_and_notify,
    schedule_usage_window_reset,
    usage_window_reset_event_id,
)
from agent_sentinel.core.store import EventStore, UsageWindow

AGENT_NAME = "gemini-cli"
WINDOW_KEY = "account"
WINDOW_DURATION = timedelta(hours=5)


def _event_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "gemini-hook-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metadata(payload: dict[str, Any]) -> dict[str, str]:
    metadata = {"hook_event": str(payload.get("hook_event_name", "unknown"))}
    for key in ("session_id", "cwd", "notification_type"):
        if payload.get(key) is not None:
            metadata[key] = str(payload[key])
    return metadata


def event_from_payload(
    payload: dict[str, Any],
    *,
    usage_window: UsageWindow | None = None,
    occurred_at: datetime | None = None,
) -> Event | None:
    """Translate Gemini CLI lifecycle and notification hooks.

    ``BeforeAgent`` starts a user-configured five-hour rolling-window estimate.
    A later rate limit in that live window creates an inferred, never exact,
    reset timestamp.
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
            if usage_window is not None:
                metadata["window_started_at"] = usage_window.started_at.isoformat()
                metadata["window_duration_seconds"] = int(WINDOW_DURATION.total_seconds())
                metadata["usage_window_reset_event_id"] = usage_window_reset_event_id(
                    AGENT_NAME, usage_window
                )
        else:
            kind = EventKind.NEEDS_USER_ACTION
            message = "Gemini CLI needs your attention."

    if kind is None:
        return None

    confidence = Confidence.UNKNOWN
    reset_at = None
    if kind is EventKind.RATE_LIMITED and usage_window is not None:
        confidence = Confidence.INFERRED
        reset_at = usage_window.reset_at
        message = "Gemini CLI is rate limited; reset time is inferred from its rolling window."

    return Event.create(
        agent=AGENT_NAME,
        kind=kind,
        occurred_at=occurred_at,
        confidence=confidence,
        reset_at=reset_at,
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
        store = EventStore()
        now = datetime.now(timezone.utc)
        if payload.get("hook_event_name") == "BeforeAgent":
            usage_window = store.begin_usage_window(AGENT_NAME, WINDOW_KEY, now, WINDOW_DURATION)
            schedule_usage_window_reset(AGENT_NAME, usage_window, store)
            return 0
        usage_window = None
        if payload.get("hook_event_name") == "Notification" and "rate limit" in str(
            payload.get("message", "")
        ).lower():
            usage_window = store.active_usage_window(AGENT_NAME, WINDOW_KEY, now)
        event = event_from_payload(payload, usage_window=usage_window, occurred_at=now)
        if event is not None:
            record_and_notify(event, store)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
