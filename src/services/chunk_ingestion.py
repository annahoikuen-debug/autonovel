"""後方互換 shim: 実体は src/engine/chunk_ingestion.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.chunk_ingestion is deprecated; use src.engine.chunk_ingestion.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.chunk_ingestion import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
