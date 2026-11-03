"""伏線メトリクスポート (F2)。

``DbForeshadowingRepository`` (infrastructure) が
``src.backend.observability`` / ``src.services`` へ直接依存せずに
ステートマシン遷移拒否を記録できるよう、記録をこのプロトコル経由に抽象化する。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ForeshadowingMetricsPort(Protocol):
    """伏線ステートマシンのメトリクス記録ポート。"""

    def record_rejection(self, reason: str) -> None:
        """遷移拒否を Prometheus メトリクスに記録する。"""
        ...
