"""Claude Code command-hook adapter.

This module only observes hook payloads and always exits successfully. A
notification integration must never interfere with Claude Code's own control
flow when an input is malformed or a local state file is temporarily
unavailable.
"""

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

AGENT_NAME = "claude-code"
WINDOW_KEY = "account"
WINDOW_DURATION = timedelta(hours=5)


def _event_id(payload: dict[str, Any]) -> str:
    """Create a repeatable id so Claude retrying an identical hook is safe."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "claude-hook-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metadata(payload: dict[str, Any]) -> dict[str, str]:
    metadata = {"hook_event": str(payload.get("hook_event_name", "unknown"))}
    for key in ("session_id", "cwd"):
        if payload.get(key) is not None:
            metadata[key] = str(payload[key])
    return metadata


def event_from_payload(
    payload: dict[str, Any],
    *,
    usage_window: UsageWindow | None = None,
    occurred_at: datetime | None = None,
) -> Event | None:
    """Translate the documented, notification-worthy Claude Code hooks.

    A ``UserPromptSubmit`` hook persists the first observed prompt in the
    five-hour Claude rolling window. When a matching rate limit follows in
    that live window, the reset is an *inferred* timestamp, never exact.
    """
    hook_event = payload.get("hook_event_name")
    kind: EventKind | None = None
    message: str | None = None
    metadata = _metadata(payload)

    if hook_event == "Stop":
        kind = EventKind.AGENT_FINISHED
        message = "Claude Code finished responding."
    elif hook_event in {"PermissionRequest", "Notification"}:
        kind = EventKind.NEEDS_USER_ACTION
        message = "Claude Code needs your attention."
    elif hook_event == "StopFailure" and payload.get("error") == "rate_limit":
        kind = EventKind.RATE_LIMITED
        message = "Claude Code is rate limited."
        metadata["error"] = "rate_limit"
        if usage_window is not None:
            metadata["window_started_at"] = usage_window.started_at.isoformat()
            metadata["window_duration_seconds"] = int(WINDOW_DURATION.total_seconds())
            metadata["usage_window_reset_event_id"] = usage_window_reset_event_id(
                AGENT_NAME, usage_window
            )

    if kind is None:
        return None

    confidence = Confidence.UNKNOWN
    reset_at = None
    if kind is EventKind.RATE_LIMITED and usage_window is not None:
        confidence = Confidence.INFERRED
        reset_at = usage_window.reset_at
        message = "Claude Code is rate limited; reset time is inferred from its rolling window."

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
    """Read one JSON hook payload from stdin and record its translated event."""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        store = EventStore()
        now = datetime.now(timezone.utc)
        if payload.get("hook_event_name") == "UserPromptSubmit":
            usage_window = store.begin_usage_window(AGENT_NAME, WINDOW_KEY, now, WINDOW_DURATION)
            schedule_usage_window_reset(AGENT_NAME, usage_window, store)
            return 0
        usage_window = None
        if payload.get("hook_event_name") == "StopFailure" and payload.get("error") == "rate_limit":
            usage_window = store.active_usage_window(AGENT_NAME, WINDOW_KEY, now)
        event = event_from_payload(payload, usage_window=usage_window, occurred_at=now)
        if event is not None:
            record_and_notify(event, store)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        # Hooks are observational. Returning a failure could block a prompt or
        # create a noisy hook error in Claude Code, so fail safely instead.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
