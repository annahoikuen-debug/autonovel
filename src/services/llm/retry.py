"""後方互換 shim: 実体は src/llm/adapters/retry.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.llm.retry is deprecated; use src.llm.adapters.retry.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.llm.adapters.retry import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
