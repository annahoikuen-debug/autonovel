"""後方互換 shim: 実体は src/engine/pipeline_base.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.pipeline_base is deprecated; use src.engine.pipeline_base.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.engine.pipeline_base import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
