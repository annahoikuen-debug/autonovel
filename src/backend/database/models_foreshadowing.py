"""ForeshadowingModel（shim for backward compatibility）。

TRACK-A7: ORM モデル実体は src/infrastructure/database/models/foreshadowing_model.py に移動。
本モジュールは後方互換のための再エクスポート shim として機能する。
"""

from __future__ import annotations

from src.infrastructure.database.models.foreshadowing_model import ForeshadowingModel  # noqa: F401

__all__ = ["ForeshadowingModel"]
