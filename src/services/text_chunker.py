"""後方互換 shim: 実体は src/engine/text_chunker.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.text_chunker is deprecated; use src.engine.text_chunker.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.text_chunker import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
