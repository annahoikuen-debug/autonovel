"""Agent memory inspection, dump and compaction API endpoints.

後方互換 shim: 実体は src/backend/routers/agent_memory.py に移設済み。
"""

from __future__ import annotations

from src.backend.routers.agent_memory import router  # noqa: F401

__all__ = ["router"]
