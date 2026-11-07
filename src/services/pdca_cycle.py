"""後方互換 shim: 実体は src/engine/pdca_cycle.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.pdca_cycle is deprecated; use src.engine.pdca_cycle.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.pdca_cycle import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
