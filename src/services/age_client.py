"""後方互換 shim: 実体は src/integrations/age_client.py に移設済み。"""
from __future__ import annotations

from src.integrations.age_client import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
