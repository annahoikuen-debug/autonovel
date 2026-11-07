"""後方互換 shim: 実体は src/llm/adapters/prompts.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.llm.prompts is deprecated; use src.llm.adapters.prompts.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.llm.adapters.prompts import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
