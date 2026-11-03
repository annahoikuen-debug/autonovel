"""FastAPI アプリケーションのエントリポイント（コンポジションルート）。

F3: 起動ロジック本体は ``src/interfaces/api/app_factory.py``、
依存の供給（配線）は ``src/backend/wiring.py`` にある。本モジュールは
両者を繋ぐ後方互換エントリポイントで、``app`` / ``create_app`` /
``lifespan`` / ``init_db`` を従来どおり再エクスポートする。
"""

from __future__ import annotations

from src.backend.database import init_db  # noqa: F401
from src.backend.wiring import build_wiring  # noqa: F401
from src.interfaces.api.app_factory import build_lifespan, create_app  # noqa: F401

wiring = build_wiring()
lifespan = build_lifespan(wiring)
app = create_app(wiring, lifespan=lifespan)

__all__ = ["app", "create_app", "build_lifespan", "lifespan", "init_db", "wiring"]
