"""API endpoints for conflict review and manual resolution.

後方互換 shim: 実体は src/backend/routers/conflicts.py に移設済み。
"""

from __future__ import annotations

from src.backend.routers.conflicts import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
