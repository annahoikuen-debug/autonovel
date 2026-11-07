"""後方互換 shim: 実体は src/engine/episode_writer.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.episode_writer is deprecated; use src.engine.episode_writer.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.episode_writer import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
