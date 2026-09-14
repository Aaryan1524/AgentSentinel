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
from typing import Any

from agent_sentinel.core.models import Confidence, Event, EventKind
from agent_sentinel.core.store import EventStore

AGENT_NAME = "claude-code"


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


def event_from_payload(payload: dict[str, Any]) -> Event | None:
    """Translate the documented, notification-worthy Claude Code hooks.

    Claude Code does not document a reset timestamp in StopFailure payloads,
    so rate-limit events intentionally remain ``unknown`` rather than making
    a false prediction. Reset inference can be added only with a documented
    rolling-window rule and a reliable window-start signal.
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
    """Read one JSON hook payload from stdin and record its translated event."""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        event = event_from_payload(payload)
        if event is not None:
            EventStore().record(event)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        # Hooks are observational. Returning a failure could block a prompt or
        # create a noisy hook error in Claude Code, so fail safely instead.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
