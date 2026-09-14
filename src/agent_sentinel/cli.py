"""Command-line entry point for the provider-neutral core."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .core.models import Confidence, Event, EventKind
from .core.store import EventStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentinel", description="Record and inspect AI coding-agent events."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    emit = subcommands.add_parser("emit", help="Record one event from an adapter or hook")
    emit.add_argument("--agent", required=True, help="Originating CLI, such as claude-code")
    emit.add_argument("--kind", choices=[kind.value for kind in EventKind], required=True)
    emit.add_argument("--id", dest="event_id", help="Stable source event id for deduplication")
    emit.add_argument("--at", dest="occurred_at", help="ISO-8601 occurrence timestamp")
    emit.add_argument("--reset-at", help="ISO-8601 reset timestamp, when known")
    emit.add_argument(
        "--confidence",
        choices=[confidence.value for confidence in Confidence],
        default=Confidence.UNKNOWN.value,
    )
    emit.add_argument("--message", help="Human-readable event detail")
    emit.add_argument("--metadata", default="{}", help="Additional event JSON object")

    status = subcommands.add_parser("status", help="Show recently recorded events")
    status.add_argument("--limit", type=int, default=20)
    status.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def _parse_metadata(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"--metadata must be valid JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError("--metadata must be a JSON object")
    return parsed


def _emit(args: argparse.Namespace, store: EventStore) -> int:
    event = Event.create(
        agent=args.agent,
        kind=args.kind,
        occurred_at=args.occurred_at,
        confidence=args.confidence,
        reset_at=args.reset_at,
        message=args.message,
        metadata=_parse_metadata(args.metadata),
        event_id=args.event_id,
    )
    inserted = store.record(event)
    print(json.dumps({"event": event.to_dict(), "recorded": inserted}, sort_keys=True))
    return 0


def _status(args: argparse.Namespace, store: EventStore) -> int:
    events = [event.to_dict() for event in store.recent(args.limit)]
    if args.json:
        print(json.dumps({"events": events}, sort_keys=True))
        return 0
    if not events:
        print("No events recorded yet.")
        return 0
    for event in events:
        reset = event["reset_at"] or "unknown"
        print(
            f"{event['occurred_at']}  {event['agent']}  {event['kind']}  "
            f"reset={reset} ({event['confidence']})"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        store = EventStore()
        if args.command == "emit":
            return _emit(args, store)
        return _status(args, store)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
