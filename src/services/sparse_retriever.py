"""後方互換 shim: 実体は src/integrations/rag/sparse_retriever.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.sparse_retriever is deprecated; use src.integrations.rag.sparse_retriever.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.integrations.rag.sparse_retriever import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
