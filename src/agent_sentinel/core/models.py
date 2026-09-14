"""The provider-neutral event contract used by Agent Sentinel."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class EventKind(str, Enum):
    """Events an adapter can report, regardless of the originating CLI."""

    AGENT_FINISHED = "agent_finished"
    NEEDS_USER_ACTION = "needs_user_action"
    RATE_LIMITED = "rate_limited"
    RESET_AVAILABLE = "reset_available"


class Confidence(str, Enum):
    """How reliable a reset timestamp is."""

    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


def _parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class Event:
    """An immutable, serializable notification-worthy agent event."""

    agent: str
    kind: EventKind
    occurred_at: datetime
    confidence: Confidence = Confidence.UNKNOWN
    reset_at: datetime | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.agent.strip():
            raise ValueError("agent must not be empty")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if self.reset_at is None and self.confidence is not Confidence.UNKNOWN:
            raise ValueError("confirmed or inferred confidence requires reset_at")
        if self.reset_at is not None and self.confidence is Confidence.UNKNOWN:
            raise ValueError("a reset_at value requires confirmed or inferred confidence")
        if self.reset_at is not None and self.reset_at.tzinfo is None:
            raise ValueError("reset_at must include a timezone")

    @classmethod
    def create(
        cls,
        *,
        agent: str,
        kind: EventKind | str,
        occurred_at: datetime | str | None = None,
        confidence: Confidence | str = Confidence.UNKNOWN,
        reset_at: datetime | str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> "Event":
        return cls(
            agent=agent,
            kind=EventKind(kind),
            occurred_at=_parse_timestamp(occurred_at or datetime.now(timezone.utc)),
            confidence=Confidence(confidence),
            reset_at=_parse_timestamp(reset_at) if reset_at is not None else None,
            message=message,
            metadata=metadata or {},
            event_id=event_id or str(uuid4()),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["confidence"] = self.confidence.value
        payload["occurred_at"] = self.occurred_at.astimezone(timezone.utc).isoformat()
        payload["reset_at"] = (
            self.reset_at.astimezone(timezone.utc).isoformat() if self.reset_at else None
        )
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Event":
        return cls.create(
            agent=payload["agent"],
            kind=payload["kind"],
            occurred_at=payload["occurred_at"],
            confidence=payload.get("confidence", Confidence.UNKNOWN),
            reset_at=payload.get("reset_at"),
            message=payload.get("message"),
            metadata=payload.get("metadata") or {},
            event_id=payload["event_id"],
        )
