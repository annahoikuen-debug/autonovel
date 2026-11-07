"""後方互換 shim: 実体は src/domain/styles.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.styles is deprecated; use src.domain.styles.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.domain.styles import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
