"""FastAPI アプリケーションのエントリポイント（shim for backward compatibility）。

TRACK-A9: 起動ロジック（lifespan, ミドルウェア, ルーター登録, エンドポイント）
は src/interfaces/api/app_factory.py に移動。
本モジュールは後方互換のための再エクスポート shim として機能する。
"""

from __future__ import annotations

from src.interfaces.api.app_factory import app, create_app, lifespan  # noqa: F401
from src.backend.database import init_db  # noqa: F401

__all__ = ["app", "create_app", "lifespan", "init_db"]
