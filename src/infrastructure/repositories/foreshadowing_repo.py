"""DB永続化版 伏線リポジトリ (v5.0 Relational Memory)

既存の InMemoryForeshadowingRepository をSQLAlchemy AsyncSession ベースに置換。
ForeshadowingModel (ORM) を直接操作し、伏線の CRUD・未回収検索・回収更新・
バランス集計をリレーショナルDBで完結する。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import and_, func, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.models.foreshadowing_status import ForeshadowingScope, ForeshadowingStatus

logger = logging.getLogger(__name__)


def _record_rejection(reason: str) -> None:
    """遷移拒否を Prometheus メトリクスに記録する（失敗しても本体処理は継続）"""
    try:
        from src.backend.observability import metrics as m

        m.foreshadowing_transitions_rejected_total.labels(reason=reason).inc()
    except Exception as e:  # pragma: no cover - メトリクス非対応環境
        logger.debug(f"Failed to record rejected foreshadowing transition: {e}")


def _allowed_predecessors(target_status: ForeshadowingStatus) -> list[str]:
    """`target_status` へ遷移できる「現在のステータス」一覧を返す。"""
    return [
        s.value for s in ForeshadowingStatus if ForeshadowingStatus.can_transition(s, target_status)
    ]


def _status_predicate(target_status: ForeshadowingStatus):
    """CAS 用のステータス述語を組み立てる。

    読み取りフェーズで判定していた内容を SQL の WHERE にそのまま埋め込むことで、
    SELECT と UPDATE の間の TOCTOU（並行実行で resolved が巻き戻る）を無くす。
    未知ステータス（手動投入・旧データ）は判断D2によりガード対象外＝素通しとするため、
    既知4値以外を OR で付け足している。
    """
    known = [s.value for s in ForeshadowingStatus]
    return or_(
        ForeshadowingModel.status.in_(_allowed_predecessors(target_status)),
        not_(ForeshadowingModel.status.in_(known)),
    )


class DbForeshadowingRepository:
    """SQLAlchemy AsyncSession ベースの伏線リポジトリ。

    既存の ForeshadowingRepository インターフェースを async 拡張して実装する。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # W5 Step 8: 直近1件の CAS 拒否理由。呼び出し側から
        # 「どの理由が何回起きたか」を外から取れるようにする。
        # スレッドセーフではない（Lock はあえて付けない。既存 InMemory 版との
        # 非対称は本計画の対象外）。
        self.last_rejection: dict[str, Any] = {}

    # ── CRUD ────────────────────────────────────────────

    async def add(self, book_id: int, title: str, description: str,
                  planted_episode: int, target_episode: Optional[int] = None,
                  scope: Optional[ForeshadowingScope] = None) -> ForeshadowingModel:
        """伏線を新規設置する

        v5.3 / Step 33: 設置時に `foreshadowing_planted_total` を記録する。
        `ForeshadowingKpiService.report_planted` は本番の呼び出し箇所が無く、
        設置件数のメトリクスが常に 0 だった。
        """
        record = ForeshadowingModel(
            book_id=book_id,
            title=title,
            description=description,
            planted_episode=planted_episode,
            target_episode=target_episode,
            status=ForeshadowingStatus.PLANTED.value,
        )
        if scope is not None:
            record.scope = scope.value
        self.db.add(record)
        await self.db.flush()
        await self._report_planted(record)
        return record

    async def _report_planted(self, record: ForeshadowingModel) -> None:
        """設置メトリクスを記録する（失敗しても設置処理は継続する）"""
        try:
            from src.services.foreshadowing.kpi import ForeshadowingKpiService

            scope = getattr(record, "scope", None) or ForeshadowingScope.SHORT_TERM.value
            await ForeshadowingKpiService(self).report_planted(
                book_id=record.book_id, scope=str(scope)
            )
        except Exception as e:  # pragma: no cover - メトリクス非対応環境
            logger.debug(f"Failed to report planted foreshadowing: {e}")

    async def get_by_id(self, foreshadowing_id: int) -> Optional[ForeshadowingModel]:
        """ID指定で伏線を取得"""
        stmt = select(ForeshadowingModel).where(ForeshadowingModel.id == foreshadowing_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ids(self, foreshadowing_ids: list[int]) -> List[ForeshadowingModel]:
        """複数ID指定で伏線一覧を取得"""
        if not foreshadowing_ids:
            return []
        stmt = (
            select(ForeshadowingModel)
            .where(ForeshadowingModel.id.in_(foreshadowing_ids))
            .order_by(ForeshadowingModel.id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_book_id(self, book_id: int) -> List[ForeshadowingModel]:
        """指定作品の全伏線を取得"""
        stmt = (
            select(ForeshadowingModel)
            .where(ForeshadowingModel.book_id == book_id)
            .order_by(ForeshadowingModel.planted_episode)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── 未回収検索（ステートマシン中核クエリ） ─────────────

    async def get_unresolved(self, book_id: int) -> List[ForeshadowingModel]:
        """指定作品の未回収伏線（planted / progressed）を全件取得

        ix_foreshadowings_book_status 複合インデックスで高速検索。
        """
        active_statuses = [s.value for s in ForeshadowingStatus.active_statuses()]
        stmt = (
            select(ForeshadowingModel)
            .where(
                ForeshadowingModel.book_id == book_id,
                ForeshadowingModel.status.in_(active_statuses),
            )
            .order_by(ForeshadowingModel.planted_episode)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_unresolved_by_scope(self, book_id: int, scope: ForeshadowingScope) -> List[ForeshadowingModel]:
        """スコープ別の未回収伏線を取得"""
        active_statuses = [s.value for s in ForeshadowingStatus.active_statuses()]
        stmt = (
            select(ForeshadowingModel)
            .where(
                ForeshadowingModel.book_id == book_id,
                ForeshadowingModel.scope == scope.value,
                ForeshadowingModel.status.in_(active_statuses),
            )
            .order_by(ForeshadowingModel.planted_episode)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_overdue(self, book_id: int, current_episode: int) -> List[ForeshadowingModel]:
        """回収期限を超過した伏線を取得（target_episode < current_episode かつ未回収）"""
        active_statuses = [s.value for s in ForeshadowingStatus.active_statuses()]
        stmt = (
            select(ForeshadowingModel)
            .where(
                ForeshadowingModel.book_id == book_id,
                ForeshadowingModel.status.in_(active_statuses),
                ForeshadowingModel.target_episode.isnot(None),
                ForeshadowingModel.target_episode < current_episode,
            )
            .order_by(ForeshadowingModel.planted_episode)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── ステータス遷移 ─────────────────────────────────

    async def _diagnose_rejection(
        self,
        foreshadowing_id: int,
        target_status: ForeshadowingStatus,
        resolved_episode: Optional[int] = None,
    ) -> str:
        """CAS 更新が rowcount=0 になった理由を特定する（拒否経路の診断専用 SELECT）。

        戻り値は従来どおり `str` だが、**`self.last_rejection` にも保存**する
        （W5-07: :callers が `False` だけを受け取れると、原因が外から消える）。
        """
        current = await self.get_by_id(foreshadowing_id)
        if current is None:
            return self._store_rejection(foreshadowing_id, target_status, "not_found")
        try:
            current_status = ForeshadowingStatus(current.status)
        except ValueError:
            current_status = None
        if current_status is not None and not ForeshadowingStatus.can_transition(
            current_status, target_status
        ):
            return self._store_rejection(
                foreshadowing_id, target_status, "illegal_transition"
            )
        if (
            isinstance(resolved_episode, int)
            and isinstance(current.planted_episode, int)
            and resolved_episode < current.planted_episode
        ):
            return self._store_rejection(
                foreshadowing_id, target_status, "before_plant_episode"
            )
        return self._store_rejection(
            foreshadowing_id, target_status, "concurrent_modification"
        )

    def _store_rejection(
        self,
        foreshadowing_id: int,
        target_status: Optional[ForeshadowingStatus],
        reason: str,
    ) -> str:
        """拒否理由を `last_rejection` に保存し、渡された `reason` をそのまま返す。"""
        self.last_rejection = {
            "id": foreshadowing_id,
            "target_status": getattr(target_status, "value", target_status),
            "reason": reason,
        }
        return reason

    async def _transition(
        self,
        foreshadowing_id: int,
        target_status: ForeshadowingStatus,
        extra_values: Optional[dict] = None,
    ) -> bool:
        """ステートマシンの遷移ガード付きで UPDATE を実行する（CAS: 単一 UPDATE）。

        終端状態（resolved / abandoned）からの巻き戻しと、
        許可されていない遷移（例: planted → planted）は rowcount=0 として拒否する。
        さらに『設置話数より前の話で回収できない』という不変条件も
        `WHERE planted_episode <= :resolved_episode` として DB 側で保証する。

        v5.3 までは SELECT→判定→WHERE 条件なし UPDATE の2往復で TOCTOU があり、
        並行実行で「回収済みの行が progressed へ巻き戻る」事故が起こり得た。
        判定条件を WHERE に埋め込んだ単一 UPDATE に変更し、往復を 2 → 1 にする。
        """
        values: dict = {
            "status": target_status.value,
            # M17: `datetime.utcnow()` は非推奨（naive datetime）。aware に統一する。
            "updated_at": datetime.now(timezone.utc),
        }
        if extra_values:
            values.update(extra_values)

        # 不変条件: resolved_episode >= planted_episode（DB 側で保証）
        resolved_ep = values.get("resolved_episode")
        conditions = [
            ForeshadowingModel.id == foreshadowing_id,
            _status_predicate(target_status),
        ]
        if isinstance(resolved_ep, int):
            conditions.append(ForeshadowingModel.planted_episode <= resolved_ep)

        stmt = (
            update(ForeshadowingModel)
            .where(and_(*conditions))
            .values(**values)
        )
        result = await self.db.execute(stmt)
        if result.rowcount > 0:
            return True

        reason = await self._diagnose_rejection(foreshadowing_id, target_status, resolved_ep)
        if reason == "before_plant_episode":
            logger.warning(
                "Rejecting foreshadowing resolution before plant episode: id=%s target=%s",
                foreshadowing_id,
                target_status.value,
            )
        else:
            logger.warning(
                "Illegal foreshadowing transition blocked: id=%s -> %s (reason=%s)",
                foreshadowing_id,
                target_status.value,
                reason,
            )
        _record_rejection(reason)
        self.last_rejection.setdefault("op", "transition")
        return False

    async def resolve(self, foreshadowing_id: int, episode_num: int) -> bool:
        """伏線を回収済みに更新"""
        return await self._transition(
            foreshadowing_id,
            ForeshadowingStatus.RESOLVED,
            {"resolved_episode": episode_num},
        )

    async def progress(self, foreshadowing_id: int) -> bool:
        """伏線を「進展中」に更新"""
        return await self._transition(foreshadowing_id, ForeshadowingStatus.PROGRESSED)

    async def abandon(self, foreshadowing_id: int) -> bool:
        """伏線を回収放棄に更新"""
        return await self._transition(foreshadowing_id, ForeshadowingStatus.ABANDONED)

    async def update_target_episode(self, foreshadowing_id: int, target_episode: int) -> bool:
        """回収予定話数を延期する（Rescheduler が使用する実API）

        v5.2 までは本メソッドが存在せず、`hasattr` ガードにより延期処理が
        サイレントに no-op になっていた（ログだけが成功を偽装）。

        v5.3: 判定を WHERE 句に埋め込んだ CAS（単一 UPDATE）に変更し、
        終端状態への巻き戻しと horizon 0（`target == planted`）を
        読み取りフェーズなしに拒否する。往復は 2 → 1。
        """
        conditions = [
            ForeshadowingModel.id == foreshadowing_id,
            # 未回収（active）な伏線だけを延期対象にする。判断D2の素通しを維持。
            or_(
                ForeshadowingModel.status.in_([s.value for s in ForeshadowingStatus.active_statuses()]),
                not_(ForeshadowingModel.status.in_([s.value for s in ForeshadowingStatus])),
            ),
            # 不変条件: 回収予定は設置話より後（horizon 0 は禁止）
            ForeshadowingModel.planted_episode < target_episode,
        ]

        stmt = (
            update(ForeshadowingModel)
            .where(and_(*conditions))
            .values(target_episode=target_episode, updated_at=datetime.now(timezone.utc))
        )
        result = await self.db.execute(stmt)
        if result.rowcount > 0:
            return True

        # 拒否理由の診断（拒否経路でのみ SELECT する。成功経路は1往復のまま）
        current = await self.get_by_id(foreshadowing_id)
        if current is None:
            reason = "not_found"
        else:
            planted_ep = getattr(current, "planted_episode", None)
            reason = "horizon_zero" if (
                isinstance(planted_ep, int) and target_episode <= planted_ep
            ) else "illegal_transition"
        logger.warning(
            "Rejecting foreshadowing reschedule: id=%s target_ep=%s (reason=%s)",
            foreshadowing_id,
            target_episode,
            reason,
        )
        _record_rejection(reason)
        self._store_rejection(foreshadowing_id, None, reason)
        self.last_rejection.setdefault("op", "update_target")
        return False

    # ── 集計 ─────────────────────────────────────────────

    async def get_balance(self, book_id: int) -> dict:
        """伏線設置/回収のバランスを取得

        Returns:
            {"planted": int, "progressed": int, "resolved": int, "abandoned": int, "active": int}
        """
        stmt = (
            select(
                ForeshadowingModel.status,
                func.count(ForeshadowingModel.id).label("count"),
            )
            .where(ForeshadowingModel.book_id == book_id)
            .group_by(ForeshadowingModel.status)
        )
        result = await self.db.execute(stmt)
        counts = {row[0]: row[1] for row in result.fetchall()}

        planted = counts.get(ForeshadowingStatus.PLANTED.value, 0)
        progressed = counts.get(ForeshadowingStatus.PROGRESSED.value, 0)
        resolved = counts.get(ForeshadowingStatus.RESOLVED.value, 0)
        abandoned = counts.get(ForeshadowingStatus.ABANDONED.value, 0)

        return {
            "planted": planted,
            "progressed": progressed,
            "resolved": resolved,
            "abandoned": abandoned,
            "active": planted + progressed,
        }
