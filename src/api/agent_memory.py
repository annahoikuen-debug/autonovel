"""Agent memory inspection, dump and compaction API endpoints.

後方互換 shim: 実体は src/backend/routers/agent_memory.py に移設済み。
"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.api.agent_memory is deprecated; use src.backend.routers.agent_memory.py instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.backend.routers.agent_memory import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
