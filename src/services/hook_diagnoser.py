"""後方互換 shim: 実体は src/engine/hook_diagnoser.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.hook_diagnoser is deprecated; use src.engine.hook_diagnoser.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.hook_diagnoser import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
