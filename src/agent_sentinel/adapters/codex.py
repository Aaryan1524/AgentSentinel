"""Adapter for the Codex CLI ``notify`` command payload."""

from __future__ import annotations

import hashlib
import json
import subprocess
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

AGENT_NAME = "codex"
WINDOW_KEY = "account"
WINDOW_DURATION = timedelta(hours=5)


def _event_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "codex-notify-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def event_from_payload(
    payload: dict[str, Any],
    *,
    usage_window: UsageWindow | None = None,
    occurred_at: datetime | None = None,
) -> Event:
    """Translate Codex's notification payload without assuming undocumented fields."""
    signal = " ".join(
        str(payload.get(key, "")) for key in ("type", "event", "status", "message")
    ).lower()
    if "rate" in signal and "limit" in signal:
        kind = EventKind.RATE_LIMITED
        message = "Codex is rate limited."
    elif any(term in signal for term in ("approval", "permission", "input", "attention")):
        kind = EventKind.NEEDS_USER_ACTION
        message = "Codex needs your attention."
    else:
        # Codex's notify command is the documented completion/attention bridge.
        kind = EventKind.AGENT_FINISHED
        message = "Codex sent a notification."
    metadata = {"notification_source": "codex"}
    for key in ("thread_id", "turn_id", "cwd"):
        if payload.get(key) is not None:
            metadata[key] = str(payload[key])
    confidence = Confidence.UNKNOWN
    reset_at = None
    if kind is EventKind.RATE_LIMITED and usage_window is not None:
        metadata["window_started_at"] = usage_window.started_at.isoformat()
        metadata["window_duration_seconds"] = int(WINDOW_DURATION.total_seconds())
        metadata["usage_window_reset_event_id"] = usage_window_reset_event_id(
            AGENT_NAME, usage_window
        )
        confidence = Confidence.INFERRED
        reset_at = usage_window.reset_at
        message = "Codex is rate limited; reset time is inferred from its rolling window."
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
            signal = " ".join(
                str(payload.get(key, "")) for key in ("type", "event", "status", "message")
            ).lower()
            usage_window = None
            if "rate" in signal and "limit" in signal:
                usage_window = store.active_usage_window(AGENT_NAME, WINDOW_KEY, now)
            record_and_notify(event_from_payload(payload, usage_window=usage_window, occurred_at=now), store)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return 0
    return 0


def run_main() -> int:
    """Start the Codex rolling-window estimate, then invoke the real CLI.

    Codex's ``notify`` callback is post-turn. This launcher supplies the
    reliable start signal needed to infer a reset when that callback later
    reports a rate limit.
    """
    try:
        store = EventStore()
        usage_window = store.begin_usage_window(
            AGENT_NAME, WINDOW_KEY, datetime.now(timezone.utc), WINDOW_DURATION
        )
        schedule_usage_window_reset(AGENT_NAME, usage_window, store)
        return subprocess.run(["codex", *sys.argv[1:]], check=False).returncode
    except (OSError, ValueError):
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
