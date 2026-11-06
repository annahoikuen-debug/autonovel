"""後方互換 shim: 実体は src/infrastructure/config/validator.py に移設済み。"""
from __future__ import annotations

from src.infrastructure.config.validator import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
