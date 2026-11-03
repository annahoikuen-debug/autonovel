"""伏線KPIポート (F2)。

``DbForeshadowingRepository`` (infrastructure) が
``src.services.foreshadowing.kpi`` へ直接依存せずに
伏線設置メトリクスを記録できるよう、記録をこのプロトコル経由に抽象化する。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ForeshadowingKpiPort(Protocol):
    """伏線KPI・設置メトリクス記録ポート。"""

    def report_planted(self, book_id: int, scope: str) -> None:
        """伏線設置をメトリクスに記録する。"""
        ...
