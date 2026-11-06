"""外部APIクライアント（後方互換 shim）。

実体は src/infrastructure/external/api_client.py に移設済み。
プライベート属性（_request 等）も含めて全属性をリダイレクトする。
patch() でのモック置き換えにも対応するため __setattr__ も実装する。
"""

from __future__ import annotations

import importlib
import sys

_api_client = importlib.import_module("src.infrastructure.external.api_client")

# 公開シンボルを再エクスポート
from src.infrastructure.external.api_client import *  # noqa: F401, F403

__all__ = [name for name in dir(_api_client) if not name.startswith("_")]


def __getattr__(name: str):
    """プライベート属性を含む全属性を実体モジュールにリダイレクト。"""
    return getattr(_api_client, name)


def __setattr__(name: str, value):
    """patch() などでの属性置き換えに対応。"""
    # 公開シンボル（__all__ に含まれるもの）は shim モジュール自体に保持し、
    # それ以外は実体モジュールに委譲する
    if name in __all__ or name in {"_api_client", "__all__", "__getattr__", "__setattr__"}:
        object.__setattr__(sys.modules[__name__], name, value)
    else:
        setattr(_api_client, name, value)
