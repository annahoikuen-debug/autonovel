"""
config/erotic_vocabulary_ext.py
エロティックボキャブラリ拡張モジュール（スタブ）。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_vocabulary_ext.py に移設済み。
"""


import warnings

warnings.warn(
    "config.erotic_vocabulary_ext is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.nsfw.erotic_vocabulary_ext import *  # noqa: F401, F403

__all__ = [
    "get_vocabulary_for_tier",
    "get_vocabulary_for_tier_ext",
]
