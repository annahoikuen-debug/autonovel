"""book_score パッケージ（成熟度評価サービス機能分割）。

src/engine/book_score/service.py から機能分割（案A+B）により新設。
旧パス ``src/engine/book_score/service.py`` は shim として残す。
"""

from __future__ import annotations

from src.engine.book_score.calculator import (
    BookScoreCalculator,
    BookScoreService,
)
from src.engine.book_score.models import BookScore
from src.engine.book_score.constants import (
    DEFAULT_DIMENSION_WEIGHTS,
    ENV_SKIP_UNAVAILABLE_WEIGHT,
    NEUTRAL_SCORE,
    ScoringUnavailableError,
    _skip_unavailable_weight,
)
from src.engine.book_score.config import (
    get_weights_for_genre_phase,
    load_book_score_config,
)

__all__ = [
    "BookScore",
    "BookScoreCalculator",
    "BookScoreService",
    "ScoringUnavailableError",
    "NEUTRAL_SCORE",
    "DEFAULT_DIMENSION_WEIGHTS",
    "ENV_SKIP_UNAVAILABLE_WEIGHT",
    "_skip_unavailable_weight",
    "load_book_score_config",
    "get_weights_for_genre_phase",
]
