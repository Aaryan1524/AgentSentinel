"""Adapter for Grok Build hook payloads."""

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

AGENT_NAME = "grok"
WINDOW_KEY = "account"
WINDOW_DURATION = timedelta(hours=5)


def _event_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "grok-hook-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def event_from_payload(
    payload: dict[str, Any],
    *,
    usage_window: UsageWindow | None = None,
    occurred_at: datetime | None = None,
) -> Event | None:
    event_name = str(payload.get("hook_event_name") or payload.get("event") or "")
    notification_type = str(payload.get("notificationType") or payload.get("notification_type") or "")
    metadata = {"hook_event": event_name}
    for key in ("session_id", "cwd", "workspace_root"):
        if payload.get(key) is not None:
            metadata[key] = str(payload[key])

    if event_name == "Stop" or notification_type == "idle_prompt":
        kind, message = EventKind.AGENT_FINISHED, "Grok finished responding."
    elif event_name == "StopFailure" and payload.get("error") == "rate_limit":
        kind, message = EventKind.RATE_LIMITED, "Grok is rate limited."
        if usage_window is not None:
            metadata["window_started_at"] = usage_window.started_at.isoformat()
            metadata["window_duration_seconds"] = int(WINDOW_DURATION.total_seconds())
            metadata["usage_window_reset_event_id"] = usage_window_reset_event_id(
                AGENT_NAME, usage_window
            )
    elif event_name == "Notification" or notification_type == "permission_prompt":
        kind, message = EventKind.NEEDS_USER_ACTION, "Grok needs your attention."
    else:
        return None
    confidence = Confidence.UNKNOWN
    reset_at = None
    if kind is EventKind.RATE_LIMITED and usage_window is not None:
        confidence = Confidence.INFERRED
        reset_at = usage_window.reset_at
        message = "Grok is rate limited; reset time is inferred from its rolling window."
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
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            store = EventStore()
            now = datetime.now(timezone.utc)
            if str(payload.get("hook_event_name") or payload.get("event") or "") == "UserPromptSubmit":
                usage_window = store.begin_usage_window(AGENT_NAME, WINDOW_KEY, now, WINDOW_DURATION)
                schedule_usage_window_reset(AGENT_NAME, usage_window, store)
                return 0
            usage_window = None
            if (
                str(payload.get("hook_event_name") or payload.get("event") or "") == "StopFailure"
                and payload.get("error") == "rate_limit"
            ):
                usage_window = store.active_usage_window(AGENT_NAME, WINDOW_KEY, now)
            event = event_from_payload(payload, usage_window=usage_window, occurred_at=now)
            if event is not None:
                record_and_notify(event, store)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
