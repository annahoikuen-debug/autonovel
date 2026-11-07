"""
config/erotic_vocabulary.py
官能ボキャブラリの定義モジュール。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_vocabulary.py に移設済み。
"""


import warnings

warnings.warn(
    "config.erotic_vocabulary is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.nsfw.erotic_vocabulary import *  # noqa: F401, F403

__all__ = [
    "METAPHOR_BANK",
    "ONOMATOPOEIA_BANK",
    "PSYCHOLOGY_TEMPLATES",
    "INTENSE_METAPHORS",
    "INTENSE_ONOMATOPOEIA",
    "INTENSE_PSYCHOLOGY",
    "VOCABULARY_TIERS",
    "get_vocabulary_for_tier",
]
