"""後方互換 shim: 実体は src/integrations/rag/reranker.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.reranker is deprecated; use src.integrations.rag.reranker.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.integrations.rag.reranker import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
