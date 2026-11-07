"""後方互換 shim: 実体は src/integrations/age_client.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.age_client is deprecated; use src.integrations.age_client.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.integrations.age_client import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
