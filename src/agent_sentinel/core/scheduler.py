"""Run due local deliveries with durable claim, retry, and history state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .models import Event
from .store import EventStore


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    event_id: str
    outcome: str
    detail: str | None = None


class LocalScheduler:
    def __init__(self, store: EventStore, deliver: Callable[[Event], None]) -> None:
        self.store = store
        self.deliver = deliver

    def run_due(self, now: datetime | None = None, dry_run: bool = False) -> list[DeliveryResult]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        results: list[DeliveryResult] = []
        for scheduled in self.store.due(current):
            event = self.store.get(scheduled.event_id)
            if event is None:
                self.store.mark_failed(scheduled.event_id, current, "scheduled event is missing")
                results.append(DeliveryResult(scheduled.event_id, "failed", "scheduled event is missing"))
                continue
            if dry_run:
                results.append(DeliveryResult(event.event_id, "would_deliver"))
                continue
            if not self.store.claim(event.event_id, current):
                continue
            try:
                self.deliver(event)
            except Exception as error:  # Delivery channels supply actionable error text.
                self.store.mark_failed(event.event_id, current, str(error))
                results.append(DeliveryResult(event.event_id, "failed", str(error)))
            else:
                self.store.mark_delivered(event.event_id, current)
                results.append(DeliveryResult(event.event_id, "delivered"))
        return results
