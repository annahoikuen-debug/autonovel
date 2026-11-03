"""
src/services/erotic_diversity_score.py - 後方互換 shim。

F4 フェーズ: 実装は src/domain/services/erotic_diversity_score.py に移設。
このモジュールは re-export 用 shim として残す。
"""

from __future__ import annotations

from src.domain.services.erotic_diversity_score import (  # noqa: F401
    check_diversity,
    check_repetition,
    classify_diversity,
    compute_diversity_score,
)
