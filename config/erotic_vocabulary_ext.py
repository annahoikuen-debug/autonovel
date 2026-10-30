"""
config/erotic_vocabulary_ext.py
エロティックボキャブラリ拡張モジュール（スタブ）。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_vocabulary_ext.py に移設済み。
"""

from src.nsfw.erotic_vocabulary_ext import *  # noqa: F401, F403

__all__ = [
    "get_vocabulary_for_tier",
    "get_vocabulary_for_tier_ext",
]
