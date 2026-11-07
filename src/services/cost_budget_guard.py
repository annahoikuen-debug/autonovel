"""後方互換 shim: 実体は src/integrations/cost_guard/budget_guard.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.cost_budget_guard is deprecated; use src.integrations.cost_guard.budget_guard.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.integrations.cost_guard.budget_guard import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
