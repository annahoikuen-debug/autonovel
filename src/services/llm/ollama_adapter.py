"""後方互換 shim: 実体は src/llm/adapters/ollama.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.llm.ollama_adapter is deprecated; use src.llm.adapters.ollama.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.llm.adapters.ollama import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
