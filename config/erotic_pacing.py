"""
config/erotic_pacing.py
官能カーブ・ビート定義モジュール。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_pacing.py に移設済み。
"""

from src.nsfw.erotic_pacing import *  # noqa: F401, F403

__all__ = [
    "EroticBeat",
    "EroticCurve",
    "EroticParameters",
    "HAS_EROTIC_PARAMETERS",
]
