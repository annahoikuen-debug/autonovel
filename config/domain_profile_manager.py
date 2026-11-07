"""後方互換 shim: 実体は src/config/domain_profile_manager.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.domain_profile_manager is deprecated; use src.config.domain_profile_manager.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.config.domain_profile_manager import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
