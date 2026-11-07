"""後方互換 shim: 実体は src/config/platform_censorship_rules.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.platform_censorship_rules is deprecated; use src.config.platform_censorship_rules.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.config.platform_censorship_rules import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
