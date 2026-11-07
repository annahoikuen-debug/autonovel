"""Unified BookScore Mapping Engine - 後方互換 shim。

F4 フェーズ: 実装は src/domain/services/book_score_mapping.py に移設。
このモジュールは re-export 用 shim として残す。
"""

from __future__ import annotations


import warnings

warnings.warn(
    "src.engine.book_score.mapping is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.domain.services.book_score_mapping import (  # noqa: F401
    BASE_TRANSFORMATION_MATRIX,
    BOOK_SCORE_DIMENSIONS,
    BookScoreResult,
    DEFAULT_DIMENSION_WEIGHTS,
    GENRE_MATRIX_OVERRIDES,
    PHASE_DIMENSION_SHIFTS,
    Unified5DScore,
    UnifiedBookScoreBridge,
)
