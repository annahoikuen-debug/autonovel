"""Dashboard data API for emotional timeline, conflicts summary and source contribution.

後方互換 shim: 実体は src/backend/routers/dashboard.py に移設済み。
"""

from __future__ import annotations

from src.backend.routers.dashboard import router  # noqa: F401

__all__ = ["router"]
