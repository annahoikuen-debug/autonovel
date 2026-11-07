"""後方互換 shim: 実体は src/integrations/rag/query_reformulator.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.query_reformulator is deprecated; use src.integrations.rag.query_reformulator.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.integrations.rag.query_reformulator import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
