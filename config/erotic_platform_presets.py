"""
config/erotic_platform_presets.py
プラットフォーム別官能プリセット定義。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_platform_presets.py に移設済み。
"""

from src.nsfw.erotic_platform_presets import *  # noqa: F401, F403

__all__ = [
    "PLATFORM_PRESETS",
    "get_preset",
    "get_preset_names",
]
