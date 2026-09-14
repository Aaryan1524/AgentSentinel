"""Safe, reversible configuration installers for supported agent CLIs."""

from .hooks import (
    apply_hooks,
    detect_adapters,
    install_codex_alias,
    remove_codex_alias,
    remove_hooks,
    target_for_adapter,
)
from .scheduler import (
    SchedulerInstallResult,
    install_scheduler,
    scheduler_is_installed,
    scheduler_paths,
    uninstall_scheduler,
)

__all__ = [
    "apply_hooks",
    "detect_adapters",
    "install_codex_alias",
    "remove_codex_alias",
    "remove_hooks",
    "target_for_adapter",
    "SchedulerInstallResult",
    "install_scheduler",
    "scheduler_is_installed",
    "scheduler_paths",
    "uninstall_scheduler",
]
