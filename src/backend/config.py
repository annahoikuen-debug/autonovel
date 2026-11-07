"""後方互換 shim: 設定の実体は ``src/infrastructure/config/settings.py``。

TRACK / F3 ポート化: 正規レイヤー（infrastructure）へ移設し、旧パス
``src.backend.config`` は再エクスポートとして維持する。
``monkeypatch.setattr(cfg_mod, "ROOT_DIR", ...)`` 等の旧来の使い方を
壊さないよう、属性は本モジュールの名前空間にも再束縛する。
"""
from __future__ import annotations


import warnings

warnings.warn(
    "src.backend.config is deprecated; use src.infrastructure.config.settings instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.config.settings import *  # noqa: F403
from src.infrastructure.config.settings import (  # noqa: F401
    ROOT_DIR,
    STORAGE_DIR,
    Settings,
    is_auth_bypass_enabled,
    is_nsfw_enabled,
    settings,
)

__all__ = [
    "ROOT_DIR",
    "STORAGE_DIR",
    "Settings",
    "is_auth_bypass_enabled",
    "is_nsfw_enabled",
    "settings",
]


def __getattr__(name: str):
    """``__all__`` 外の名前も旧パスから引き続き解決できるようにする（PEP 562）。"""
    from src.infrastructure.config import settings as _settings_module

    return getattr(_settings_module, name)
