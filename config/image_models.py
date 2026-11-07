"""後方互換 shim: 実体は src/config/image_models.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.image_models is deprecated; use src.config.image_models.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.config.image_models import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
