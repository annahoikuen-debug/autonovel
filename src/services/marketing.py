"""後方互換 shim: 実体は src/integrations/marketing/marketing.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.marketing is deprecated; use src.integrations.marketing.marketing.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.integrations.marketing.marketing import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
