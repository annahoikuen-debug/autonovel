"""後方互換 shim: 実体は src/llm/adapters/base.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.llm.base is deprecated; use src.llm.adapters.base.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.llm.adapters.base import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
