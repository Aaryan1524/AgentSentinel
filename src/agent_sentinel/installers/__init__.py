"""Safe, reversible configuration installers for supported agent CLIs."""

from .hooks import apply_hooks, detect_adapters, remove_hooks

__all__ = ["apply_hooks", "detect_adapters", "remove_hooks"]
