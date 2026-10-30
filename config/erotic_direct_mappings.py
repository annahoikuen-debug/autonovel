"""
config/erotic_direct_mappings.py
直接表現→比喩表現のマッピング定義。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_direct_mappings.py に移設済み。
"""

from src.nsfw.erotic_direct_mappings import *  # noqa: F401, F403

__all__ = [
    "DIRECT_TO_METAPHOR",
    "EXTRA_ABSTRACTIONS",
    "get_combined_mappings",
]
