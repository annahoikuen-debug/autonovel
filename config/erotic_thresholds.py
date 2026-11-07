"""
config/erotic_thresholds.py
官能関連のスコア閾値を定義する。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_thresholds.py に移設済み。
"""


import warnings

warnings.warn(
    "config.erotic_thresholds is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.nsfw.erotic_thresholds import *  # noqa: F401, F403

__all__ = [
    "DIVERSITY_SCORE_PASS",
    "DIVERSITY_SCORE_WARN",
    "DIVERSITY_SCORE_FAIL",
    "INTENSITY_R15",
    "INTENSITY_SAFE_MAX",
    "INTENSITY_EXTREME",
    "AFTERGLOW_MIN_PARAGRAPHS",
    "AFTERGLOW_MIN_CHARS",
    "MAX_CONSECUTIVE_PEAK_EPISODES",
]
