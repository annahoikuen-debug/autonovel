"""後方互換 shim: 実体は src/infrastructure/config/project_context.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.project_context is deprecated; use src.infrastructure.config.project_context.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.infrastructure.config.project_context import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
