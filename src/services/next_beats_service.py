"""後方互換 shim: 実体は src/engine/next_beats_service.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.next_beats_service is deprecated; use src.engine.next_beats_service.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.next_beats_service import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
