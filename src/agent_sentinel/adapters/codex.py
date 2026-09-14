"""Adapter for the Codex CLI ``notify`` command payload."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from agent_sentinel.core.models import Confidence, Event, EventKind
from agent_sentinel.core.store import EventStore


def _event_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "codex-notify-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def event_from_payload(payload: dict[str, Any]) -> Event:
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
    return Event.create(
        agent="codex",
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
            EventStore().record(event_from_payload(payload))
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
