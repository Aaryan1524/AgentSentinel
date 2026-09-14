"""Command-line entry point for the provider-neutral core."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .channels import QStashChannel, TelegramChannel
from .core.models import Confidence, Event, EventKind
from .core.scheduler import LocalScheduler
from .core.store import EventStore, default_state_path
from .installers import (
    apply_hooks,
    detect_adapters,
    install_codex_alias,
    install_scheduler,
    remove_codex_alias,
    remove_hooks,
    scheduler_is_installed,
    scheduler_paths,
    target_for_adapter,
    uninstall_scheduler,
)


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

    notify = subcommands.add_parser("notify", help="Deliver a stored event now")
    notify.add_argument("--id", dest="event_id", required=True, help="Recorded event ID")
    notify.add_argument("--channel", choices=["telegram"], default="telegram")
    notify.add_argument("--dry-run", action="store_true", help="Render without sending")

    schedule = subcommands.add_parser("schedule", help="Schedule a stored event for local delivery")
    schedule.add_argument("--id", dest="event_id", required=True, help="Recorded event ID")
    schedule.add_argument("--at", required=True, help="ISO-8601 delivery time with timezone")

    run_due = subcommands.add_parser("run-due", help="Deliver all due locally scheduled events")
    run_due.add_argument("--dry-run", action="store_true", help="Show due events without sending")

    deliveries = subcommands.add_parser("deliveries", help="Show local delivery history")
    deliveries.add_argument("--limit", type=int, default=20)
    deliveries.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    init = subcommands.add_parser("init", help="Detect supported CLIs and safely add Sentinel hooks")
    init.add_argument("--detect", action="store_true", help="Configure every detected supported CLI")
    init.add_argument(
        "--adapter",
        choices=["claude-code", "gemini-cli", "grok-build", "codex-cli"],
        action="append",
    )
    init.add_argument(
        "--codex-alias",
        action="store_true",
        help="Explicitly add a managed zsh/bash alias so codex runs through sentinel-codex",
    )
    init.add_argument("--dry-run", action="store_true", help="Show changes without editing settings")
    init.add_argument("--home", help="Override home directory, useful for automation and tests")

    uninstall = subcommands.add_parser("uninstall", help="Safely remove Sentinel hook configuration")
    uninstall.add_argument("--detect", action="store_true", help="Remove hooks from every detected supported CLI")
    uninstall.add_argument(
        "--adapter",
        choices=["claude-code", "gemini-cli", "grok-build", "codex-cli"],
        action="append",
    )
    uninstall.add_argument(
        "--codex-alias",
        action="store_true",
        help="Remove only the managed Codex launcher alias from zsh/bash",
    )
    uninstall.add_argument("--dry-run", action="store_true", help="Show changes without editing settings")
    uninstall.add_argument("--home", help="Override home directory, useful for automation and tests")

    scheduler = subcommands.add_parser("scheduler", help="Install or inspect the local due-delivery runner")
    scheduler_commands = scheduler.add_subparsers(dest="scheduler_command", required=True)
    install_scheduler_command = scheduler_commands.add_parser("install")
    install_scheduler_command.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    install_scheduler_command.add_argument("--home", help="Override home directory, useful for automation and tests")
    install_scheduler_command.add_argument(
        "--no-activate", action="store_true", help="Write configuration without activating it now"
    )
    install_scheduler_command.add_argument(
        "--executable", help="Absolute Sentinel executable path for the background runner"
    )
    uninstall_scheduler_command = scheduler_commands.add_parser("uninstall")
    uninstall_scheduler_command.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    uninstall_scheduler_command.add_argument("--home", help="Override home directory, useful for automation and tests")
    status_scheduler = scheduler_commands.add_parser("status")
    status_scheduler.add_argument("--home", help="Override home directory, useful for automation and tests")

    doctor = subcommands.add_parser("doctor", help="Check local notification setup without sending a message")
    doctor.add_argument("--home", help="Override home directory, useful for automation and tests")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable diagnostics")
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


def _notify(args: argparse.Namespace, store: EventStore) -> int:
    event = store.get(args.event_id)
    if event is None:
        raise ValueError(f"event not found: {args.event_id}")
    if args.dry_run:
        print(TelegramChannel.render(event))
        return 0
    channel = TelegramChannel.from_environment()
    channel.send(event)
    print(json.dumps({"delivered": True, "event_id": event.event_id, "channel": args.channel}))
    return 0


def _schedule(args: argparse.Namespace, store: EventStore) -> int:
    scheduled = store.schedule(args.event_id, args.at)
    print(json.dumps({"event_id": scheduled.event_id, "due_at": scheduled.due_at.isoformat()}))
    return 0


def _run_due(args: argparse.Namespace, store: EventStore) -> int:
    channel = TelegramChannel.from_environment() if not args.dry_run else None
    scheduler = LocalScheduler(store, channel.send if channel else lambda _event: None)
    results = scheduler.run_due(dry_run=args.dry_run)
    print(json.dumps({"deliveries": [asdict(result) for result in results]}, sort_keys=True))
    return 0


def _deliveries(args: argparse.Namespace, store: EventStore) -> int:
    history = [
        {
            "event_id": entry.event_id,
            "due_at": entry.due_at.isoformat(),
            "status": entry.status,
            "attempt_count": entry.attempt_count,
            "delivered_at": entry.delivered_at.isoformat() if entry.delivered_at else None,
            "last_error": entry.last_error,
        }
        for entry in store.schedules(args.limit)
    ]
    if args.json:
        print(json.dumps({"deliveries": history}, sort_keys=True))
        return 0
    if not history:
        print("No scheduled deliveries yet.")
        return 0
    for entry in history:
        print(f"{entry['due_at']}  {entry['event_id']}  {entry['status']}  attempts={entry['attempt_count']}")
    return 0


def _targets_for_request(args: argparse.Namespace, home: Path | None) -> list:
    detected = detect_adapters(home)
    available = {target.name: target for target in detected}
    requested = list(dict.fromkeys(args.adapter or []))
    targets = list(detected) if args.detect else []
    for name in requested:
        target = available.get(name)
        if target is None:
            if name in {"grok-build", "codex-cli"}:
                target = target_for_adapter(name, home)
            else:
                raise ValueError(f"settings file not found for: {name}")
        if target.name not in {entry.name for entry in targets}:
            targets.append(target)
    return targets


def _init(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser() if args.home else None
    targets = _targets_for_request(args, home)
    if not targets:
        if args.codex_alias:
            raise ValueError("--codex-alias requires --adapter codex-cli or a detected Codex CLI configuration")
        print(json.dumps({"configured": [], "message": "No supported CLI settings files detected."}))
        return 0
    results = [apply_hooks(target, args.dry_run) for target in targets]
    if args.codex_alias and "codex-cli" not in {target.name for target in targets}:
        raise ValueError("--codex-alias requires --adapter codex-cli or a detected Codex CLI configuration")
    alias_result = install_codex_alias(home, dry_run=args.dry_run) if args.codex_alias else None
    print(
        json.dumps(
            {
                "configured": [
                    {
                        "adapter": result.adapter,
                        "settings_path": str(result.settings_path),
                        "changed": result.changed,
                        "backup_path": str(result.backup_path) if result.backup_path else None,
                    }
                    for result in results
                ],
                "codex_alias": (
                    {
                        "profile_path": str(alias_result.profile_path),
                        "changed": alias_result.changed,
                        "backup_path": str(alias_result.backup_path)
                        if alias_result.backup_path
                        else None,
                    }
                    if alias_result
                    else None
                ),
                "dry_run": args.dry_run,
            },
            sort_keys=True,
        )
    )
    return 0


def _uninstall(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser() if args.home else None
    targets = _targets_for_request(args, home)
    results = [remove_hooks(target, args.dry_run) for target in targets]
    if args.codex_alias and "codex-cli" not in {target.name for target in targets}:
        raise ValueError("--codex-alias requires --adapter codex-cli or a detected Codex CLI configuration")
    alias_result = remove_codex_alias(home, dry_run=args.dry_run) if args.codex_alias else None
    print(
        json.dumps(
            {
                "uninstalled": [
                    {
                        "adapter": result.adapter,
                        "settings_path": str(result.settings_path),
                        "changed": result.changed,
                        "backup_path": str(result.backup_path) if result.backup_path else None,
                    }
                    for result in results
                ],
                "codex_alias": (
                    {
                        "profile_path": str(alias_result.profile_path),
                        "changed": alias_result.changed,
                        "backup_path": str(alias_result.backup_path)
                        if alias_result.backup_path
                        else None,
                    }
                    if alias_result
                    else None
                ),
                "dry_run": args.dry_run,
            },
            sort_keys=True,
        )
    )
    return 0


def _scheduler(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser() if getattr(args, "home", None) else None
    if args.scheduler_command == "status":
        paths = scheduler_paths(home)
        print(
            json.dumps(
                {"paths": [str(path) for path in paths], "installed": scheduler_is_installed(home)}
            )
        )
        return 0
    if args.scheduler_command == "install":
        executable = args.executable or shutil.which("sentinel") or "sentinel"
        result = install_scheduler(
            home=home,
            executable=executable,
            dry_run=args.dry_run,
            activate=not args.no_activate,
        )
    else:
        result = uninstall_scheduler(home=home, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                "platform": result.platform,
                "paths": [str(path) for path in result.paths],
                "changed": result.changed,
                "backups": [str(path) for path in result.backups],
                "activated": result.activated,
                "dry_run": args.dry_run,
            },
            sort_keys=True,
        )
    )
    return 0


def _doctor(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser() if args.home else Path.home()
    state_path = default_state_path()
    if args.home:
        state_path = home / ".agent-sentinel" / "state.sqlite3"
    checks: list[dict[str, str]] = []
    checks.append(
        {
            "name": "state_directory",
            "status": "ok" if state_path.parent.exists() else "warning",
            "detail": str(state_path),
        }
    )
    try:
        TelegramChannel.from_environment()
    except (OSError, ValueError):
        checks.append(
            {
                "name": "telegram",
                "status": "warning",
                "detail": "Telegram credentials are not configured.",
            }
        )
    else:
        checks.append({"name": "telegram", "status": "ok", "detail": "credentials configured"})
    try:
        QStashChannel.from_environment()
    except (OSError, ValueError):
        checks.append(
            {
                "name": "qstash",
                "status": "warning",
                "detail": "QStash is not configured; reset delivery needs this computer online.",
            }
        )
    else:
        checks.append({"name": "qstash", "status": "ok", "detail": "offline delivery configured"})
    adapters = detect_adapters(home)
    if adapters:
        for adapter in adapters:
            try:
                has_sentinel_hook = "sentinel-" in adapter.settings_path.read_text()
            except OSError:
                has_sentinel_hook = False
            checks.append(
                {
                    "name": f"adapter:{adapter.name}",
                    "status": "ok" if has_sentinel_hook else "warning",
                    "detail": str(adapter.settings_path),
                }
            )
    else:
        checks.append({"name": "adapters", "status": "warning", "detail": "no supported settings found"})
    checks.append(
        {
            "name": "scheduler",
            "status": "ok" if scheduler_is_installed(home) else "warning",
            "detail": "installed" if scheduler_is_installed(home) else "not installed",
        }
    )
    healthy = all(check["status"] == "ok" for check in checks)
    if args.json:
        print(json.dumps({"healthy": healthy, "checks": checks}, sort_keys=True))
    else:
        for check in checks:
            print(f"{check['status'].upper():7} {check['name']}: {check['detail']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "uninstall":
            return _uninstall(args)
        if args.command == "scheduler":
            return _scheduler(args)
        if args.command == "doctor":
            return _doctor(args)
        store = EventStore()
        if args.command == "emit":
            return _emit(args, store)
        if args.command == "status":
            return _status(args, store)
        if args.command == "notify":
            return _notify(args, store)
        if args.command == "schedule":
            return _schedule(args, store)
        if args.command == "run-due":
            return _run_due(args, store)
        return _deliveries(args, store)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
