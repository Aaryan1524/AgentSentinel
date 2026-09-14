"""Bridge Aider's custom completion-notification command into Sentinel."""

from __future__ import annotations

from agent_sentinel.core.models import Confidence, Event, EventKind
from agent_sentinel.core.store import EventStore


def event() -> Event:
    """Aider invokes this command after its response and before user input."""
    return Event.create(
        agent="aider",
        kind=EventKind.NEEDS_USER_ACTION,
        confidence=Confidence.UNKNOWN,
        message="Aider finished responding and is waiting for your input.",
        metadata={"notification_source": "aider"},
    )


def main() -> int:
    try:
        EventStore().record(event())
    except (OSError, ValueError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
