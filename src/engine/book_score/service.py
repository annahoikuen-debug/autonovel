"""src/engine/book_score/service.py — 後方互換 shim。

実装は ``src/engine/book_score/`` パッケージ（calculator.py 等）に移設済み。
このモジュールは旧 import 経路（``from src.engine.book_score.service import ...``）を
維持するためにパッケージから再エクスポートする。

分割は案A+B（ファイル隔離＋旧パスshim＋関連テスト全緑）に従う。
削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。
"""

from __future__ import annotations

import warnings

warnings.warn(
    "src.engine.book_score.service is deprecated; use src.engine.book_score package instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.engine.book_score import (  # noqa: F401, F403
    BookScore,
    BookScoreCalculator,
    BookScoreService,
    ScoringUnavailableError,
    NEUTRAL_SCORE,
    DEFAULT_DIMENSION_WEIGHTS,
    ENV_SKIP_UNAVAILABLE_WEIGHT,
    _skip_unavailable_weight,
    load_book_score_config,
    get_weights_for_genre_phase,
)

__all__ = [name for name in dir() if not name.startswith("_")]
