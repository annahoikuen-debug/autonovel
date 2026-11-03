"""伏線ポートの本番実装 (backend 層)。

``src.domain.ports`` で定義したポートを ``src.backend.observability.metrics`` で
実装する。backend 層なので旧モノリスへの依存は契約2 の対象外。
"""

from __future__ import annotations

from src.backend.observability import metrics as m
from src.domain.ports.foreshadowing_kpi import ForeshadowingKpiPort
from src.domain.ports.foreshadowing_metrics import ForeshadowingMetricsPort


class BackendForeshadowingMetricsPort(ForeshadowingMetricsPort):
    """ForeshadowingMetricsPort の src.backend.observability.metrics 実装。"""

    def record_rejection(self, reason: str) -> None:
        m.foreshadowing_transitions_rejected_total.labels(reason=reason).inc()


class BackendForeshadowingKpiPort(ForeshadowingKpiPort):
    """ForeshadowingKpiPort の src.backend.observability.metrics 実装。"""

    def report_planted(self, book_id: int, scope: str) -> None:
        m.foreshadowing_planted_total.labels(scope=scope).inc()
