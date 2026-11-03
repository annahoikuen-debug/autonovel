"""Prometheus / Huey メトリクスルーターのファクトリ（TRACK-A9 / F3）。

メトリクス公開の実体（``metrics_endpoint``）と Huey 状態は旧レイヤー
（``src.backend``）にあり、interfaces からは直接 import できないため、
配線側（コンポジションルート）から注入してルーターを構築する。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter


def build_metrics_router(
    *,
    metrics_endpoint: Callable[[], Awaitable[Any]],
    huey_status: Callable[[], dict[str, Any]] | None = None,
) -> APIRouter:
    """メトリクスルーターを構築する。

    ``huey_status`` を渡した場合のみ非推奨の
    ``/metrics/huey-sqlite-busy`` エンドポイントを登録する。
    """
    router = APIRouter(tags=["metrics"])

    @router.get("/metrics")
    async def prometheus_metrics():
        """Prometheus 形式でメトリクスを公開"""
        return await metrics_endpoint()

    if huey_status is not None:

        # 既存の huey-sqlite-busy エンドポイントは互換性のため残却、非推奨化
        @router.get("/metrics/huey-sqlite-busy", deprecated=True)
        async def huey_sqlite_busy_metrics():
            """Deprecated: Use /metrics instead"""
            return huey_status()

    return router
