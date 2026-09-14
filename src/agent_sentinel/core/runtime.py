"""Fail-open runtime behavior shared by every external-agent adapter."""

from __future__ import annotations

from agent_sentinel.channels.telegram import TelegramChannel
from agent_sentinel.channels.qstash import QStashChannel

from .models import Event, EventKind
from .store import EventStore, UsageWindow


def usage_window_reset_event_id(agent: str, usage_window: UsageWindow) -> str:
    """Return the id shared by every observation of one rolling window."""
    return f"{agent}-window-reset-{int(usage_window.reset_at.timestamp())}"


def schedule_usage_window_reset(
    agent: str, usage_window: UsageWindow, store: EventStore | None = None
) -> str:
    """Queue one off-device reset notification when a window first starts.

    Recording first makes repeated prompt hooks idempotent. QStash is the
    preferred delivery path; the local runner remains a fallback for users who
    have not configured QStash or are temporarily offline at window start.
    """
    event_store = store or EventStore()
    event_id = usage_window_reset_event_id(agent, usage_window)
    reset_event = Event.create(
        agent=agent,
        kind=EventKind.RESET_AVAILABLE,
        occurred_at=usage_window.reset_at,
        confidence="inferred",
        reset_at=usage_window.reset_at,
        message=f"{agent} may be available again; this reset time is inferred.",
        metadata={
            "window_started_at": usage_window.started_at.isoformat(),
            "window_duration_seconds": int(
                (usage_window.reset_at - usage_window.started_at).total_seconds()
            ),
        },
        event_id=event_id,
    )
    if not event_store.record(reset_event):
        return event_id
    try:
        QStashChannel.from_environment().schedule(reset_event)
    except (OSError, RuntimeError, ValueError):
        event_store.schedule(reset_event.event_id, reset_event.reset_at)
    return event_id


def _reset_available_event(event: Event) -> Event | None:
    """Create the one future notification implied by a timed rate limit."""
    if event.kind is not EventKind.RATE_LIMITED or event.reset_at is None:
        return None
    if event.metadata.get("usage_window_reset_event_id"):
        # The start hook has already queued the one reset notification for this
        # rolling window. Do not create a duplicate when the limit is reached.
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
        try:
            QStashChannel.from_environment().schedule(reset_event)
        except (OSError, RuntimeError, ValueError):
            # The local scheduler remains a durable fallback when a user has
            # not enabled QStash or the scheduling request is temporarily down.
            event_store.schedule(reset_event.event_id, reset_event.reset_at)
    try:
        TelegramChannel.from_environment().send(event)
    except (OSError, RuntimeError, ValueError):
        pass
    return True
