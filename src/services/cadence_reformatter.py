"""後方互換 shim: 実体は ``src/application/formatters/cadence_reformatter.py``。"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.cadence_reformatter is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.application.formatters.cadence_reformatter import (  # noqa: F401
    CadenceReformatter,
    CadenceStats,
    cadence_reformatter,
)

__all__ = ["CadenceReformatter", "CadenceStats", "cadence_reformatter"]
