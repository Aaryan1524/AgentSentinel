"""Safe, reversible configuration installers for supported agent CLIs."""

from .hooks import apply_hooks, detect_adapters, remove_hooks
from .scheduler import SchedulerInstallResult, install_scheduler, scheduler_paths, uninstall_scheduler

__all__ = [
    "apply_hooks",
    "detect_adapters",
    "remove_hooks",
    "SchedulerInstallResult",
    "install_scheduler",
    "scheduler_paths",
    "uninstall_scheduler",
]
