"""後方互換 shim: 実体は src/domain/models/config_models.py に移設済み。"""
from __future__ import annotations


import warnings

warnings.warn(
    "config.models is deprecated; use src.domain.models.config_models.py instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.domain.models.config_models import *  # noqa: F401, F403

__all__ = [name for name in dir() if not name.startswith("_")]
