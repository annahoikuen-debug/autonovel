"""後方互換 shim: 実体は src/engine/blind_review.py に移設済み。"""
from __future__ import annotations

from src.engine.blind_review import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
