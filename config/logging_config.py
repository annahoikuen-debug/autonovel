"""後方互換 shim: 実体は src/infrastructure/config/logging_config.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.logging_config is deprecated; use src.infrastructure.config.logging_config.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.infrastructure.config.logging_config import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
