"""
config/erotic_parameters.py
官能エージェント用の調整可能なパラメータ定義モジュール。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_parameters.py に移設済み。
"""

from src.nsfw.erotic_parameters import *  # noqa: F401, F403

__all__ = [
    "DEFAULT_SENSORY_WEIGHTS",
    "DEFAULT_PACE_RATIOS",
    "EroticParameters",
]
