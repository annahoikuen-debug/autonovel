"""後方互換 shim: 実体は src/llm/adapters/vllm.py に移設済み。"""
from __future__ import annotations

from src.llm.adapters.vllm import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
