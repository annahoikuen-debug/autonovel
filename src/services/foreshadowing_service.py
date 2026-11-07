"""後方互換 shim: 実体は src/engine/foreshadowing/service.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.foreshadowing_service is deprecated; use src.engine.foreshadowing.service.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.foreshadowing.service import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
