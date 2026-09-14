"""Fail-open runtime behavior shared by every external-agent adapter."""

from __future__ import annotations

from agent_sentinel.channels.telegram import TelegramChannel

from .models import Event
from .store import EventStore


def record_and_notify(event: Event, store: EventStore | None = None) -> bool:
    """Record once, then notify once when Telegram credentials are configured.

    External hooks must never block their parent agent. Delivery errors remain
    observable through the agent's own output/state, but always fail open here.
    """
    event_store = store or EventStore()
    recorded = event_store.record(event)
    if not recorded:
        return False
    try:
        TelegramChannel.from_environment().send(event)
    except (OSError, RuntimeError, ValueError):
        pass
    return True
