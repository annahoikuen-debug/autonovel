"""後方互換 shim: 実体は src/backend/routers/admin_phase2.py に移設済み。"""

from __future__ import annotations

from src.backend.routers.admin_phase2 import (  # noqa: F401
    enrichment_router,
    rag_router,
    router,
)

__all__ = ["enrichment_router", "rag_router", "router"]
