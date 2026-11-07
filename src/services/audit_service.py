"""後方互換 shim: 実体は src/engine/audit/service.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.audit_service is deprecated; use src.engine.audit.service.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.audit.service import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
