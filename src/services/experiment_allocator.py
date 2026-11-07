"""Experiment Allocator for A/B Testing - 後方互換 shim。

F4 フェーズ: 実装は src/domain/services/experiment_allocator.py に移設。
このモジュールは re-export 用 shim として残す。
"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.services.experiment_allocator is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.domain.services.experiment_allocator import (  # noqa: F401
    DEFAULT_ALLOCATOR,
    ExperimentAllocator,
    MultiExperimentAllocator,
    allocate_variant,
)
