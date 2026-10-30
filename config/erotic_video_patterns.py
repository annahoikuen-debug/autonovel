"""
config/erotic_video_patterns.py
エロ動画の映像パターンを文学技法に変換するマッピング定義。

本ファイルはインターフェース互換のための shim です。
実装は src/nsfw/erotic_video_patterns.py に移設済み。
"""

from src.nsfw.erotic_video_patterns import *  # noqa: F401, F403

__all__ = [
    "VideoPattern",
    "VIDEO_PATTERNS",
    "get_pattern",
    "get_patterns_for_intensity",
    "get_patterns_by_sensory_focus",
    "get_literary_instructions_for_pattern",
    "get_all_pattern_instructions",
]
