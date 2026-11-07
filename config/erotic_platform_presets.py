"""
config/erotic_platform_presets.py
プラットフォーム別官能プリセット定義。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_platform_presets.py に移設済み。
"""


import warnings

warnings.warn(
    "config.erotic_platform_presets is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.nsfw.erotic_platform_presets import *  # noqa: F401, F403

__all__ = [
    "PLATFORM_PRESETS",
    "get_preset",
    "get_preset_names",
]
