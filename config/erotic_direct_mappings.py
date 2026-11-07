"""
config/erotic_direct_mappings.py
直接表現→比喩表現のマッピング定義。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_direct_mappings.py に移設済み。
"""


import warnings

warnings.warn(
    "config.erotic_direct_mappings is deprecated; use docs/MOVEMENT_MAPPING.md (移設先一覧) instead",
    DeprecationWarning,
    stacklevel=2,
)
from src.nsfw.erotic_direct_mappings import *  # noqa: F401, F403

__all__ = [
    "DIRECT_TO_METAPHOR",
    "EXTRA_ABSTRACTIONS",
    "get_combined_mappings",
]
