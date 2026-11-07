"""後方互換 shim: 実体は src/engine/quality_scorer.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.quality_scorer is deprecated; use src.engine.quality_scorer.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.quality_scorer import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
