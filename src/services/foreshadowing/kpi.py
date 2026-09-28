"""伏線KPIサービス (v5.3 長編耐性の定量化)

ロードマップが掲げる主要KPI「伏線回収率」を実測可能にする。

v5.2 までは `DbForeshadowingRepository.get_balance` が 완성しているのに
本番から一度も呼ばれておらず、伏線に関する Prometheus メトリクスも 0 個だった。
つまり「伏線がどれだけ回収されているか」を数値で追う手段が存在しなかった。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Optional

from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
from src.models.foreshadowing_status import ForeshadowingStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForeshadowingKpi:
    """作品1件の伏線KPIスナップショット"""

    book_id: int
    planted: int
    progressed: int
    resolved: int
    abandoned: int
    active: int
    overdue: int
    collection_rate: float
    resolution_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


class ForeshadowingKpiService:
    """伏線回収率などのKPIを算出・メトリクス反映するサービス。"""

    def __init__(self, repo: DbForeshadowingRepository):
        self.repo = repo

    async def compute(self, book_id: int, current_episode: Optional[int] = None) -> ForeshadowingKpi:
        """伏線KPIを算出する。

        Args:
            book_id: 作品ID
            current_episode: 現在話数（指定時は期限超過を計測する）

        Returns:
            ForeshadowingKpi
        """
        balance = await self.repo.get_balance(book_id)

        overdue = 0
        if current_episode is not None:
            try:
                overdue = len(await self.repo.get_overdue(book_id, current_episode))
            except Exception as e:  # pragma: no cover - 計測は失敗しても本処理を落とさない
                logger.debug(f"Failed to compute overdue foreshadowings: {e}")

        planted = int(balance.get("planted", 0))
        progressed = int(balance.get("progressed", 0))
        resolved = int(balance.get("resolved", 0))
        abandoned = int(balance.get("abandoned", 0))
        active = planted + progressed
        terminal = resolved + abandoned

        kpi = ForeshadowingKpi(
            book_id=book_id,
            planted=planted,
            progressed=progressed,
            resolved=resolved,
            abandoned=abandoned,
            active=active,
            overdue=overdue,
            # 回収率 = 終端状態になったうち実際に回収された割合
            collection_rate=_ratio(resolved, terminal),
            # 解決率 = 設置された伏線のうち終端状態に達した割合
            resolution_rate=_ratio(terminal, terminal + active),
        )
        self._publish(kpi)
        return kpi

    def _publish(self, kpi: ForeshadowingKpi) -> None:
        """Prometheus メトリクスへ反映する（失敗しても本体処理は継続する）"""
        try:
            from src.backend.observability import metrics as m

            m.foreshadowing_active_gauge.labels(book_id=str(kpi.book_id)).set(kpi.active)
            m.foreshadowing_overdue_gauge.labels(book_id=str(kpi.book_id)).set(kpi.overdue)
            m.foreshadowing_collection_rate.labels(book_id=str(kpi.book_id)).set(
                kpi.collection_rate
            )
        except Exception as e:  # pragma: no cover - メトリクス非対応環境
            logger.debug(f"Failed to publish foreshadowing metrics: {e}")

    async def report_planted(self, book_id: int, scope: str) -> None:
        """伏線設置をメトリクスに記録する"""
        try:
            from src.backend.observability import metrics as m

            m.foreshadowing_planted_total.labels(scope=scope).inc()
        except Exception as e:  # pragma: no cover
            logger.debug(f"Failed to report planted foreshadowing: {e}")

    async def report_transition(
        self, from_status: str, to_status: str, rejected_reason: Optional[str] = None
    ) -> None:
        """ステートマシンの遷移（または遷移拒否）をメトリクスに記録する"""
        try:
            from src.backend.observability import metrics as m

            if rejected_reason:
                m.foreshadowing_transitions_rejected_total.labels(reason=rejected_reason).inc()
                return
            m.foreshadowing_status_transitions_total.labels(
                from_status=from_status, to_status=to_status
            ).inc()
        except Exception as e:  # pragma: no cover
            logger.debug(f"Failed to report foreshadowing transition: {e}")

    async def report_rescheduled(self, book_id: int) -> None:
        """伏線延期をメトリクスに記録する"""
        try:
            from src.backend.observability import metrics as m

            m.foreshadowing_rescheduled_total.labels(book_id=str(book_id)).inc()
        except Exception as e:  # pragma: no cover
            logger.debug(f"Failed to report rescheduled foreshadowing: {e}")


def terminal_statuses() -> tuple[str, ...]:
    """終端状態の値一覧（KPI計算の共通定義）"""
    return tuple(s.value for s in ForeshadowingStatus if s.is_terminal)
