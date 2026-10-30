"""Platform export router (shim for backward compatibility).

TRACK-A8: ルーター実体は src/interfaces/api/platform_export.py に移設。
本モジュールは後方互換のための再エクスポート shim として機能する。
"""

from __future__ import annotations

from src.interfaces.api.platform_export import router  # noqa: F401

__all__ = ["router"]
