"""後方互換 shim: 実体は src/engine/graph_pipeline.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.graph_pipeline is deprecated; use src.engine.graph_pipeline.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.graph_pipeline import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
