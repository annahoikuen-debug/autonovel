"""後方互換 shim: 実体は src/infrastructure/config/file_watcher.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.file_watcher is deprecated; use src.infrastructure.config.file_watcher.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.infrastructure.config.file_watcher import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
