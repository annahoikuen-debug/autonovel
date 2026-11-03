"""Metrics router（旧パス互換の配線 shim）。

TRACK-A8 / F3: ルーター実体のファクトリは ``src/interfaces/api/metrics.py``
にあり、Prometheus 実体と Huey 状態は旧レイヤーのため、本モジュール
（コンポジションルート）が注入して構築する。旧 import 経路
``src.backend.routers.metrics.router`` は全パスを提供し続ける。
"""

from __future__ import annotations

from typing import Any

from src.backend.observability.metrics import metrics_endpoint
from src.interfaces.api.metrics import build_metrics_router


def _huey_status() -> dict[str, Any]:
    """Huey キューの積載状況（旧レイヤー ``src.backend.tasks`` に依存）。"""
    from src.backend.tasks import huey

    try:
        pending_count = huey.pending_count()
        backend_class = huey.backend.__class__.__name__ if hasattr(huey, "backend") else "unknown"
        return {
            "huey_sqlite_busy_total": pending_count,
            "huey_backend": "sqlite"
            if "Sqlite" in backend_class
            else "redis"
            if "Redis" in backend_class
            else "unknown",
        }
    except Exception:
        return {"huey_sqlite_busy_total": 0, "huey_backend": "unknown"}


router = build_metrics_router(metrics_endpoint=metrics_endpoint, huey_status=_huey_status)

__all__ = ["router"]
