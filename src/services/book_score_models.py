"""後方互換 shim: 実体は src/engine/book_score/models.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.book_score_models is deprecated; use src.engine.book_score.models.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.book_score.models import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
