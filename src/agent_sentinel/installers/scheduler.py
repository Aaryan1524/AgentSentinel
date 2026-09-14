"""Install the local due-delivery runner without replacing user configuration."""

from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


LABEL = "com.agentsentinel.run-due"
WINDOWS_TASK = "AgentSentinel-RunDue"
INTERVAL_SECONDS = 60
MARKER = "# Managed by Agent Sentinel"


@dataclass(frozen=True, slots=True)
class SchedulerInstallResult:
    platform: str
    paths: tuple[Path, ...]
    changed: bool
    backups: tuple[Path, ...]
    activated: bool


def _platform_name(system_name: str | None = None) -> str:
    detected = system_name or platform.system()
    if detected in {"Darwin", "Linux", "Windows"}:
        return detected
    raise ValueError(f"local scheduler installation is not supported on {detected} yet")


def _backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.agent-sentinel.{stamp}.bak")
    sequence = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.agent-sentinel.{stamp}.{sequence}.bak")
        sequence += 1
    backup.write_bytes(path.read_bytes())
    return backup


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.agent-sentinel.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _macos_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _linux_paths(home: Path) -> tuple[Path, Path]:
    root = home / ".config" / "systemd" / "user"
    return root / "agent-sentinel.service", root / "agent-sentinel.timer"


def _macos_content(executable: str, home: Path) -> bytes:
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": [executable, "run-due"],
            "StartInterval": INTERVAL_SECONDS,
            "RunAtLoad": True,
            "StandardOutPath": str(home / ".agent-sentinel" / "scheduler.log"),
            "StandardErrorPath": str(home / ".agent-sentinel" / "scheduler-error.log"),
        },
        sort_keys=True,
    )


def _linux_content(executable: str) -> tuple[bytes, bytes]:
    service = f"""{MARKER}
[Unit]
Description=Deliver due Agent Sentinel notifications

[Service]
Type=oneshot
ExecStart={executable} run-due
""".encode()
    timer = f"""{MARKER}
[Unit]
Description=Run Agent Sentinel delivery every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec={INTERVAL_SECONDS}s
Persistent=true

[Install]
WantedBy=timers.target
""".encode()
    return service, timer


def scheduler_paths(home: Path | None = None, system_name: str | None = None) -> tuple[Path, ...]:
    """Return the platform-specific files the scheduler installer owns."""
    root = (home or Path.home()).expanduser()
    system = _platform_name(system_name)
    if system == "Darwin":
        return (_macos_path(root),)
    if system == "Linux":
        return _linux_paths(root)
    return (Path("Task Scheduler") / WINDOWS_TASK,)


def _run(command: list[str], runner: object | None = None) -> subprocess.CompletedProcess[str]:
    execute = runner or subprocess.run
    return execute(command, text=True, capture_output=True, check=False)  # type: ignore[no-any-return]


def _windows_task_query(runner: object | None = None) -> subprocess.CompletedProcess[str]:
    return _run(["schtasks", "/Query", "/TN", WINDOWS_TASK, "/XML"], runner)


def _is_owned_windows_task(output: str) -> bool:
    normalized = output.lower()
    return "sentinel" in normalized and "run-due" in normalized


def _activate(paths: tuple[Path, ...], system_name: str, runner: object | None = None) -> None:
    if system_name == "Darwin":
        command = ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(paths[0])]
        commands = (command,)
    elif system_name == "Linux":
        commands = (
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", "agent-sentinel.timer"],
        )
    else:
        return
    for command in commands:
        if shutil.which(command[0]) is None:
            raise OSError(f"{command[0]} is required to activate the local scheduler")
        completed = _run(command, runner)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "activation failed"
            raise OSError(f"could not activate local scheduler: {detail}")


def _deactivate(paths: tuple[Path, ...], system_name: str, runner: object | None = None) -> None:
    if system_name == "Darwin":
        commands = (["launchctl", "bootout", f"gui/{os.getuid()}", str(paths[0])],)
    elif system_name == "Linux":
        commands = (
            ["systemctl", "--user", "disable", "--now", "agent-sentinel.timer"],
            ["systemctl", "--user", "daemon-reload"],
        )
    else:
        return
    for command in commands:
        if shutil.which(command[0]) is not None:
            _run(command, runner)


def install_scheduler(
    *,
    home: Path | None = None,
    executable: str = "sentinel",
    dry_run: bool = False,
    activate: bool = True,
    system_name: str | None = None,
    runner: object | None = None,
) -> SchedulerInstallResult:
    """Install a per-user minute-level due-delivery job with backups."""
    root = (home or Path.home()).expanduser()
    system = _platform_name(system_name)
    paths = scheduler_paths(root, system)
    if system == "Windows":
        existing = _windows_task_query(runner)
        if existing.returncode == 0 and not _is_owned_windows_task(existing.stdout):
            raise ValueError(f"refusing to replace unmanaged scheduled task: {WINDOWS_TASK}")
        changed = existing.returncode != 0
        if dry_run or not changed:
            return SchedulerInstallResult(system, paths, changed, (), False)
        task_command = f'"{executable}" run-due'
        created = _run(
            [
                "schtasks", "/Create", "/TN", WINDOWS_TASK, "/SC", "MINUTE", "/MO", str(INTERVAL_SECONDS // 60),
                "/TR", task_command,
            ],
            runner,
        )
        if created.returncode != 0:
            detail = created.stderr.strip() or created.stdout.strip() or "task creation failed"
            raise OSError(f"could not activate local scheduler: {detail}")
        return SchedulerInstallResult(system, paths, True, (), True)
    contents = (_macos_content(executable, root),) if system == "Darwin" else _linux_content(executable)
    changes = [(path, content) for path, content in zip(paths, contents) if not path.exists() or path.read_bytes() != content]
    if dry_run or not changes:
        return SchedulerInstallResult(system, paths, bool(changes), (), False)

    (root / ".agent-sentinel").mkdir(parents=True, exist_ok=True)
    backups = []
    for path, content in changes:
        if path.exists():
            backups.append(_backup(path))
        _atomic_write(path, content)
    if activate:
        _activate(paths, system, runner)
    return SchedulerInstallResult(system, paths, True, tuple(backups), activate)


def uninstall_scheduler(
    *,
    home: Path | None = None,
    dry_run: bool = False,
    deactivate: bool = True,
    system_name: str | None = None,
    runner: object | None = None,
) -> SchedulerInstallResult:
    """Remove only scheduler files recognizable as Agent Sentinel-owned."""
    system = _platform_name(system_name)
    paths = scheduler_paths(home, system)
    if system == "Windows":
        existing = _windows_task_query(runner)
        if existing.returncode != 0:
            return SchedulerInstallResult(system, paths, False, (), False)
        if not _is_owned_windows_task(existing.stdout):
            raise ValueError(f"refusing to remove unmanaged scheduled task: {WINDOWS_TASK}")
        if dry_run:
            return SchedulerInstallResult(system, paths, True, (), False)
        removed = _run(["schtasks", "/Delete", "/TN", WINDOWS_TASK, "/F"], runner)
        if removed.returncode != 0:
            detail = removed.stderr.strip() or removed.stdout.strip() or "task removal failed"
            raise OSError(f"could not remove local scheduler: {detail}")
        return SchedulerInstallResult(system, paths, True, (), False)
    existing = [path for path in paths if path.exists()]
    if system == "Darwin":
        for path in existing:
            try:
                if plistlib.loads(path.read_bytes()).get("Label") != LABEL:
                    raise ValueError(f"refusing to remove unmanaged scheduler file: {path}")
            except plistlib.InvalidFileException as error:
                raise ValueError(f"refusing to remove invalid scheduler file: {path}") from error
    else:
        for path in existing:
            if not path.read_text().startswith(MARKER):
                raise ValueError(f"refusing to remove unmanaged scheduler file: {path}")
    if dry_run or not existing:
        return SchedulerInstallResult(system, paths, bool(existing), (), False)
    if deactivate:
        _deactivate(paths, system, runner)
    backups = []
    for path in existing:
        backups.append(_backup(path))
        path.unlink()
    return SchedulerInstallResult(system, paths, True, tuple(backups), False)


def scheduler_is_installed(
    home: Path | None = None, system_name: str | None = None, runner: object | None = None
) -> bool:
    """Report whether the platform-owned scheduler is currently configured."""
    system = _platform_name(system_name)
    if system == "Windows":
        task = _windows_task_query(runner)
        return task.returncode == 0 and _is_owned_windows_task(task.stdout)
    return all(path.exists() for path in scheduler_paths(home, system))
