"""後方互換 shim: 実体は src/engine/foreshadowing/service.py に移設済み。"""
from __future__ import annotations

from src.engine.foreshadowing.service import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
