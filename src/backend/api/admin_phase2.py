"""後方互換 shim: 実体は src/backend/routers/admin_phase2.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.backend.api.admin_phase2 is deprecated; use src.backend.routers.admin_phase2.py instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.backend.routers.admin_phase2 import (  # noqa: F401
    enrichment_router,
    rag_router,
    router,
)

__all__ = ["enrichment_router", "rag_router", "router"]
