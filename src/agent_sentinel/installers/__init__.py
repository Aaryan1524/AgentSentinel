"""Safe, reversible configuration installers for supported agent CLIs."""

from .hooks import apply_hooks, detect_adapters

__all__ = ["apply_hooks", "detect_adapters"]
