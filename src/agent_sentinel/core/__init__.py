"""Stable core contracts shared by every CLI adapter and delivery channel."""

from .models import Confidence, Event, EventKind
from .store import EventStore

__all__ = ["Confidence", "Event", "EventKind", "EventStore"]
