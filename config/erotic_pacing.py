"""
config/erotic_pacing.py
官能カーブ・ビート定義モジュール。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_pacing.py に移設済み。
"""


import warnings

warnings.warn(
    "config.erotic_pacing is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.nsfw.erotic_pacing import *  # noqa: F401, F403

__all__ = [
    "EroticBeat",
    "EroticCurve",
    "EroticParameters",
    "HAS_EROTIC_PARAMETERS",
]
