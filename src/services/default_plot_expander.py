"""後方互換 shim: 実体は src/engine/default_plot_expander.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.default_plot_expander is deprecated; use src.engine.default_plot_expander.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.default_plot_expander import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
