"""後方互換 shim: 実体は src/engine/conflict_report_service.py に移設済み。"""
from __future__ import annotations

from src.engine.conflict_report_service import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
