"""
src/nsfw - 官能(NSFW)分離モジュール群

config/erotic_*.py から移設した官能コンテンツ関連モジュールを
パッケージ化したもの。config/ 側の erotic_*.py は shim として
こちらから再エクスポートすることで従来の import 経路を維持する。
"""

from . import (
    erotic_direct_mappings,
    erotic_parameters,
    erotic_pacing,
    erotic_platform_presets,
    erotic_thresholds,
    erotic_video_patterns,
    erotic_vocabulary,
    erotic_vocabulary_ext,
)

__all__ = [
    "erotic_direct_mappings",
    "erotic_parameters",
    "erotic_pacing",
    "erotic_platform_presets",
    "erotic_thresholds",
    "erotic_video_patterns",
    "erotic_vocabulary",
    "erotic_vocabulary_ext",
]
