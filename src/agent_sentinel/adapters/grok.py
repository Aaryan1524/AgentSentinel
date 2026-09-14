"""Adapter for Grok Build hook payloads."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from agent_sentinel.core.models import Confidence, Event, EventKind
from agent_sentinel.core.runtime import record_and_notify


def _event_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "grok-hook-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def event_from_payload(payload: dict[str, Any]) -> Event | None:
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
    elif event_name == "Notification" or notification_type == "permission_prompt":
        kind, message = EventKind.NEEDS_USER_ACTION, "Grok needs your attention."
    else:
        return None
    return Event.create(
        agent="grok",
        kind=kind,
        confidence=Confidence.UNKNOWN,
        message=message,
        metadata=metadata,
        event_id=_event_id(payload),
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            event = event_from_payload(payload)
            if event is not None:
                record_and_notify(event)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
