"""後方互換 shim: 実体は src/publishing/formatters/style_distiller.py に移設済み。"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.services.style_distiller is deprecated; use src.publishing.formatters.style_distiller.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.publishing.formatters.style_distiller import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
