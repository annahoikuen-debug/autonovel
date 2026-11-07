"""後方互換 shim: ログ設定の実体は ``src/infrastructure/logging_config.py``。

TRACK / F3 ポート化: 正規レイヤー（infrastructure）へ移設し、旧パス
``src.backend.logging_config`` は再エクスポートとして維持する。
テストが参照するプライベート名（``_ContextFilter`` 等）も PEP 562 の
モジュール ``__getattr__`` で引き続き解決できる。
"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.backend.logging_config is deprecated; use src.infrastructure.config.logging_config instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.logging_config import *  # noqa: F403
from src.infrastructure.logging_config import (  # noqa: F401
    _is_text_mode,
    configure,
    get_logger,
)

__all__ = ["configure", "get_logger", "_is_text_mode"]


def __getattr__(name: str):
    """``__all__`` 外の名前（プライベート補助関数含む）も旧パスから解決する。"""
    from src.infrastructure import logging_config as _impl

    return getattr(_impl, name)
