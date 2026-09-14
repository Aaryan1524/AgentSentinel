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


@dataclass(frozen=True, slots=True)
class ShellAliasResult:
    profile_path: Path
    changed: bool
    backup_path: Path | None


def detect_adapters(home: Path | None = None) -> list[AdapterTarget]:
    root = (home or Path.home()).expanduser()
    candidates = (
        AdapterTarget("claude-code", root / ".claude" / "settings.json"),
        AdapterTarget("gemini-cli", root / ".gemini" / "settings.json"),
        AdapterTarget("grok-build", root / ".grok" / "hooks" / "agent-sentinel.json"),
        AdapterTarget("codex-cli", root / ".codex" / "config.toml"),
    )
    return [
        target
        for target in candidates
        if target.settings_path.exists()
        or (target.name == "grok-build" and (root / ".grok").exists())
        or (target.name == "codex-cli" and (root / ".codex").exists())
    ]


def target_for_adapter(adapter: str, home: Path | None = None) -> AdapterTarget:
    """Return the configuration target, including safely creatable targets."""
    root = (home or Path.home()).expanduser()
    targets = {
        "claude-code": AdapterTarget("claude-code", root / ".claude" / "settings.json"),
        "gemini-cli": AdapterTarget("gemini-cli", root / ".gemini" / "settings.json"),
        "grok-build": AdapterTarget("grok-build", root / ".grok" / "hooks" / "agent-sentinel.json"),
        "codex-cli": AdapterTarget("codex-cli", root / ".codex" / "config.toml"),
    }
    try:
        return targets[adapter]
    except KeyError as error:
        raise ValueError(f"unsupported adapter: {adapter}") from error


def _command_for(adapter: str) -> str:
    commands = {
        "claude-code": "sentinel-claude-hook",
        "gemini-cli": "sentinel-gemini-hook",
        "grok-build": "sentinel-grok-hook",
    }
    try:
        return commands[adapter]
    except KeyError as error:
        raise ValueError(f"unsupported hook adapter: {adapter}") from error


def _hook_groups(adapter: str) -> dict[str, list[dict[str, Any]]]:
    command = _command_for(adapter)
    if adapter == "claude-code":
        return {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command}]}],
            "Stop": [{"hooks": [{"type": "command", "command": command}]}],
            "PermissionRequest": [{"hooks": [{"type": "command", "command": command}]}],
            "Notification": [{"hooks": [{"type": "command", "command": command}]}],
            "StopFailure": [
                {"matcher": "rate_limit", "hooks": [{"type": "command", "command": command}]}
            ],
        }
    if adapter == "gemini-cli":
        return {
            "BeforeAgent": [{"matcher": "*", "hooks": [{"type": "command", "command": command}]}],
            "AfterAgent": [{"matcher": "*", "hooks": [{"type": "command", "command": command}]}],
            "Notification": [{"matcher": "*", "hooks": [{"type": "command", "command": command}]}],
        }
    if adapter == "grok-build":
        return {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command}]}],
            "Stop": [{"hooks": [{"type": "command", "command": command}]}],
            "Notification": [{"hooks": [{"type": "command", "command": command}]}],
            "StopFailure": [
                {"matcher": "rate_limit", "hooks": [{"type": "command", "command": command}]}
            ],
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


def _write_text_with_backup(path: Path, content: str) -> Path | None:
    backup: Path | None = None
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.agent-sentinel.{stamp}.bak")
        sequence = 1
        while backup.exists():
            backup = path.with_name(f"{path.name}.agent-sentinel.{stamp}.{sequence}.bak")
            sequence += 1
        backup.write_bytes(path.read_bytes())
        if os.name == "posix":
            os.chmod(backup, 0o600)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.agent-sentinel.tmp")
    try:
        temporary.write_text(content)
        if os.name == "posix":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return backup


def _write_with_backup(path: Path, settings: dict[str, Any]) -> Path | None:
    return _write_text_with_backup(path, json.dumps(settings, indent=2) + "\n")


def _apply_codex_notify(target: AdapterTarget, dry_run: bool) -> InstallResult:
    if target.settings_path.exists():
        content = target.settings_path.read_text()
    else:
        content = ""
    notify_lines = [
        line for line in content.splitlines() if line.strip().startswith("notify") and "=" in line
    ]
    managed_line = 'notify = ["sentinel-codex-notify"]'
    if notify_lines:
        if any("sentinel-codex-notify" in line for line in notify_lines):
            return InstallResult(target.name, target.settings_path, False, None)
        raise ValueError(
            f"{target.settings_path} already defines notify; refusing to replace the user's notification command"
        )
    updated = f"{content.rstrip()}\n\n{managed_line}\n" if content.strip() else f"{managed_line}\n"
    if dry_run:
        return InstallResult(target.name, target.settings_path, True, None)
    backup = _write_text_with_backup(target.settings_path, updated)
    return InstallResult(target.name, target.settings_path, True, backup)


def _remove_codex_notify(target: AdapterTarget, dry_run: bool) -> InstallResult:
    if not target.settings_path.exists():
        return InstallResult(target.name, target.settings_path, False, None)
    content = target.settings_path.read_text()
    managed_line = 'notify = ["sentinel-codex-notify"]'
    lines = content.splitlines()
    retained = [line for line in lines if line.strip() != managed_line]
    if len(retained) == len(lines):
        return InstallResult(target.name, target.settings_path, False, None)
    updated = "\n".join(retained).rstrip() + "\n"
    if dry_run:
        return InstallResult(target.name, target.settings_path, True, None)
    backup = _write_text_with_backup(target.settings_path, updated)
    return InstallResult(target.name, target.settings_path, True, backup)


_CODEX_ALIAS_START = "# >>> Agent Sentinel Codex launcher >>>"
_CODEX_ALIAS_END = "# <<< Agent Sentinel Codex launcher <<<"
_CODEX_ALIAS_BLOCK = f"{_CODEX_ALIAS_START}\nalias codex='sentinel-codex'\n{_CODEX_ALIAS_END}\n"


def _codex_profile(home: Path, shell: str | None = None) -> Path:
    shell_name = Path(shell or os.environ.get("SHELL", "")).name
    profiles = {"zsh": ".zshrc", "bash": ".bashrc"}
    try:
        return home / profiles[shell_name]
    except KeyError as error:
        raise ValueError(
            "Codex alias installation supports zsh and bash; run sentinel-codex directly for other shells"
        ) from error


def install_codex_alias(
    home: Path | None = None, *, shell: str | None = None, dry_run: bool = False
) -> ShellAliasResult:
    """Add an explicit, removable alias so normal ``codex`` starts Sentinel."""
    profile = _codex_profile((home or Path.home()).expanduser(), shell)
    content = profile.read_text() if profile.exists() else ""
    if _CODEX_ALIAS_START in content:
        return ShellAliasResult(profile, False, None)
    if any(line.lstrip().startswith("alias codex=") for line in content.splitlines()):
        raise ValueError(f"{profile} already defines a codex alias; refusing to replace it")
    updated = f"{content.rstrip()}\n\n{_CODEX_ALIAS_BLOCK}" if content.strip() else _CODEX_ALIAS_BLOCK
    if dry_run:
        return ShellAliasResult(profile, True, None)
    return ShellAliasResult(profile, True, _write_text_with_backup(profile, updated))


def remove_codex_alias(
    home: Path | None = None, *, shell: str | None = None, dry_run: bool = False
) -> ShellAliasResult:
    """Remove only the managed Codex launcher block from a shell profile."""
    profile = _codex_profile((home or Path.home()).expanduser(), shell)
    if not profile.exists():
        return ShellAliasResult(profile, False, None)
    content = profile.read_text()
    if _CODEX_ALIAS_START not in content or _CODEX_ALIAS_END not in content:
        return ShellAliasResult(profile, False, None)
    start = content.index(_CODEX_ALIAS_START)
    end = content.index(_CODEX_ALIAS_END, start) + len(_CODEX_ALIAS_END)
    updated = (content[:start] + content[end:]).strip() + "\n"
    if dry_run:
        return ShellAliasResult(profile, True, None)
    return ShellAliasResult(profile, True, _write_text_with_backup(profile, updated))


def apply_hooks(target: AdapterTarget, dry_run: bool = False) -> InstallResult:
    """Append only missing Sentinel command groups and retain a full backup."""
    if target.name == "codex-cli":
        return _apply_codex_notify(target, dry_run)
    settings = _load_settings(target.settings_path) if target.settings_path.exists() else {}
    hooks = settings.setdefault("hooks", {})
    changed = False
    command = _command_for(target.name)
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
    if target.name == "codex-cli":
        return _remove_codex_notify(target, dry_run)
    if not target.settings_path.exists():
        return InstallResult(target.name, target.settings_path, False, None)
    settings = _load_settings(target.settings_path)
    hooks = settings.get("hooks", {})
    command = _command_for(target.name)
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
