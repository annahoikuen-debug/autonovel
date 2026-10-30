"""Metrics router (shim for backward compatibility).

TRACK-A8: ルーター実体は src/interfaces/api/metrics.py に移設。
本モジュールは後方互換のための再エクスポート shim として機能する。
"""

from __future__ import annotations

from src.interfaces.api.metrics import router  # noqa: F401

__all__ = ["router"]
