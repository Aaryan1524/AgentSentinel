"""Fail-open runtime behavior shared by every external-agent adapter."""

from __future__ import annotations

from agent_sentinel.channels.telegram import TelegramChannel

from .models import Event, EventKind
from .store import EventStore


def _reset_available_event(event: Event) -> Event | None:
    """Create the one future notification implied by a timed rate limit."""
    if event.kind is not EventKind.RATE_LIMITED or event.reset_at is None:
        return None
    return Event.create(
        agent=event.agent,
        kind=EventKind.RESET_AVAILABLE,
        occurred_at=event.reset_at,
        confidence=event.confidence,
        reset_at=event.reset_at,
        message=f"{event.agent} may be available again; this reset time is {event.confidence.value}.",
        metadata={"source_event_id": event.event_id, **event.metadata},
        event_id=f"{event.event_id}-reset-available",
    )


def record_and_notify(event: Event, store: EventStore | None = None) -> bool:
    """Record once, then notify once when Telegram credentials are configured.

    External hooks must never block their parent agent. Delivery errors remain
    observable through the agent's own output/state, but always fail open here.
    """
    event_store = store or EventStore()
    recorded = event_store.record(event)
    if not recorded:
        return False
    reset_event = _reset_available_event(event)
    if reset_event is not None:
        event_store.record(reset_event)
        event_store.schedule(reset_event.event_id, reset_event.reset_at)
    try:
        TelegramChannel.from_environment().send(event)
    except (OSError, RuntimeError, ValueError):
        pass
    return True
