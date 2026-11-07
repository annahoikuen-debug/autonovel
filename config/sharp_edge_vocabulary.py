"""後方互換 shim: 実体は src/config/sharp_edge_vocabulary.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.sharp_edge_vocabulary is deprecated; use src.config.sharp_edge_vocabulary.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.config.sharp_edge_vocabulary import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
