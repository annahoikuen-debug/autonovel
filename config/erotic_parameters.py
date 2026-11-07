"""
config/erotic_parameters.py
官能エージェント用の調整可能なパラメータ定義モジュール。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_parameters.py に移設済み。
"""


import warnings

warnings.warn(
    "config.erotic_parameters is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.nsfw.erotic_parameters import *  # noqa: F401, F403

__all__ = [
    "DEFAULT_SENSORY_WEIGHTS",
    "DEFAULT_PACE_RATIOS",
    "EroticParameters",
]
