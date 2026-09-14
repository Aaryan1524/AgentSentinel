"""Safely merge Agent Sentinel hook groups into CLI settings files."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AdapterTarget:
    name: str
    settings_path: Path


@dataclass(frozen=True, slots=True)
class InstallResult:
    adapter: str
    settings_path: Path
    changed: bool
    backup_path: Path | None


def detect_adapters(home: Path | None = None) -> list[AdapterTarget]:
    root = (home or Path.home()).expanduser()
    candidates = (
        AdapterTarget("claude-code", root / ".claude" / "settings.json"),
        AdapterTarget("gemini-cli", root / ".gemini" / "settings.json"),
    )
    return [target for target in candidates if target.settings_path.exists()]


def _hook_groups(adapter: str) -> dict[str, list[dict[str, Any]]]:
    command = "sentinel-claude-hook" if adapter == "claude-code" else "sentinel-gemini-hook"
    if adapter == "claude-code":
        return {
            "Stop": [{"hooks": [{"type": "command", "command": command}]}],
            "PermissionRequest": [{"hooks": [{"type": "command", "command": command}]}],
            "Notification": [{"hooks": [{"type": "command", "command": command}]}],
            "StopFailure": [
                {"matcher": "rate_limit", "hooks": [{"type": "command", "command": command}]}
            ],
        }
    if adapter == "gemini-cli":
        return {
            "AfterAgent": [{"matcher": "*", "hooks": [{"type": "command", "command": command}]}],
            "Notification": [{"matcher": "*", "hooks": [{"type": "command", "command": command}]}],
        }
    raise ValueError(f"unsupported adapter: {adapter}")


def _contains_command(groups: list[Any], command: str) -> bool:
    return any(
        isinstance(group, dict)
        and any(
            isinstance(hook, dict) and hook.get("command") == command
            for hook in group.get("hooks", [])
        )
        for group in groups
    )


def _load_settings(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error.msg}") from error
    if not isinstance(loaded, dict):
        raise ValueError(f"settings root in {path} must be a JSON object")
    if "hooks" in loaded and not isinstance(loaded["hooks"], dict):
        raise ValueError(f"hooks in {path} must be a JSON object")
    return loaded


def _write_with_backup(path: Path, settings: dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.agent-sentinel.{stamp}.bak")
    sequence = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.agent-sentinel.{stamp}.{sequence}.bak")
        sequence += 1
    backup.write_bytes(path.read_bytes())
    temporary = path.with_suffix(".json.agent-sentinel.tmp")
    try:
        temporary.write_text(json.dumps(settings, indent=2) + "\n")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return backup


def apply_hooks(target: AdapterTarget, dry_run: bool = False) -> InstallResult:
    """Append only missing Sentinel command groups and retain a full backup."""
    settings = _load_settings(target.settings_path)
    hooks = settings.setdefault("hooks", {})
    changed = False
    command = "sentinel-claude-hook" if target.name == "claude-code" else "sentinel-gemini-hook"
    for event, additions in _hook_groups(target.name).items():
        existing = hooks.setdefault(event, [])
        if not isinstance(existing, list):
            raise ValueError(f"hooks.{event} in {target.settings_path} must be a JSON array")
        if not _contains_command(existing, command):
            existing.extend(additions)
            changed = True

    if not changed or dry_run:
        return InstallResult(target.name, target.settings_path, changed, None)

    backup = _write_with_backup(target.settings_path, settings)
    return InstallResult(target.name, target.settings_path, True, backup)


def remove_hooks(target: AdapterTarget, dry_run: bool = False) -> InstallResult:
    """Remove Sentinel commands only, retaining other commands in each group."""
    settings = _load_settings(target.settings_path)
    hooks = settings.get("hooks", {})
    command = "sentinel-claude-hook" if target.name == "claude-code" else "sentinel-gemini-hook"
    changed = False
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            raise ValueError(f"hooks.{event} in {target.settings_path} must be a JSON array")
        retained_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                retained_groups.append(group)
                continue
            retained_hooks = [
                hook
                for hook in group["hooks"]
                if not (isinstance(hook, dict) and hook.get("command") == command)
            ]
            if len(retained_hooks) == len(group["hooks"]):
                retained_groups.append(group)
            elif retained_hooks:
                retained_groups.append({**group, "hooks": retained_hooks})
                changed = True
            else:
                changed = True
        if retained_groups:
            hooks[event] = retained_groups
        elif groups:
            del hooks[event]

    if not changed or dry_run:
        return InstallResult(target.name, target.settings_path, changed, None)
    backup = _write_with_backup(target.settings_path, settings)
    return InstallResult(target.name, target.settings_path, True, backup)
