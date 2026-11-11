"""階層的ダイジェストロールアップの DB リポジトリ (PLAN_M1 Step 5).

`DigestRollupModel` の upsert / 取得 / 失効検出を担う。
`EpisodeDigestRepository`（`src/engine/context_compression/digest_service.py`）
と同じ AsyncSession 注入・flush() ベースのスタイルに合わせる。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database.models_rollup import DigestRollupModel


class DigestRollupRepository:
    """エピソードダイジェストロールアップの非同期DBリポジトリ。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_rollup(
        self,
        book_id: int,
        level: str,
        start_ep: int,
        end_ep: int,
        digest_text: str,
        stale_at: Optional[datetime] = None,
    ) -> DigestRollupModel:
        """(book_id, level, start_ep, end_ep) の UNIQUE キーで冪等 upsert する。

        既存レコードがあれば digest_text / updated_at を更新し、
        なければ新規作成する。`stale_at` は明示的に渡されたときのみ更新。
        """
        stmt = (
            select(DigestRollupModel)
            .where(DigestRollupModel.book_id == book_id)
            .where(DigestRollupModel.level == level)
            .where(DigestRollupModel.start_ep == start_ep)
            .where(DigestRollupModel.end_ep == end_ep)
        )
        res = await self.db.execute(stmt)
        existing = res.scalars().first()

        now = datetime.now(timezone.utc)
        if existing:
            existing.digest_text = digest_text
            existing.updated_at = now
            # stale_at は常に上書き（None でクリア、値で設定）。
            # Step 14 で stale 解消時に stale_at=None を渡すため。
            existing.stale_at = stale_at
            await self.db.flush()
            return existing

        record = DigestRollupModel(
            book_id=book_id,
            level=level,
            start_ep=start_ep,
            end_ep=end_ep,
            digest_text=digest_text,
            stale_at=stale_at,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_rollups(
        self,
        book_id: int,
        level: str,
    ) -> List[DigestRollupModel]:
        """指定作品・粒度のロールアップを start_ep 昇順で取得する。"""
        stmt = (
            select(DigestRollupModel)
            .where(DigestRollupModel.book_id == book_id)
            .where(DigestRollupModel.level == level)
            .order_by(DigestRollupModel.start_ep.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def find_stale(self, book_id: int) -> List[DigestRollupModel]:
        """stale_at が設定されている（失効済みの）ロールアップを取得する。"""
        stmt = (
            select(DigestRollupModel)
            .where(DigestRollupModel.book_id == book_id)
            .where(DigestRollupModel.stale_at.is_not(None))
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def mark_stale_for_episode(
        self,
        book_id: int,
        episode_num: int,
        cfg: Any,
    ) -> None:
        """episode_num が属する章・巻 rollup を stale_at 設定で失効させる。

        次回の digest 保存時に該当 rollup の再生成トリガとなる（PLAN_M1 Step 14）。
        """
        block_per_volume = cfg.episodes_per_block * cfg.blocks_per_volume

        # 章(ブロック)境界
        block_start = (
            (episode_num - 1) // cfg.episodes_per_block
        ) * cfg.episodes_per_block + 1
        block_end = block_start + cfg.episodes_per_block - 1
        await self._set_stale(book_id, "block", block_start, block_end)

        # 巻境界
        volume_start = (
            (episode_num - 1) // block_per_volume
        ) * block_per_volume + 1
        volume_end = volume_start + block_per_volume - 1
        await self._set_stale(book_id, "volume", volume_start, volume_end)

    async def _set_stale(
        self,
        book_id: int,
        level: str,
        start_ep: int,
        end_ep: int,
    ) -> None:
        """該当 rollup レコードの stale_at / updated_at を現在時刻にする。"""
        stmt = (
            select(DigestRollupModel)
            .where(DigestRollupModel.book_id == book_id)
            .where(DigestRollupModel.level == level)
            .where(DigestRollupModel.start_ep == start_ep)
            .where(DigestRollupModel.end_ep == end_ep)
        )
        res = await self.db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            now = datetime.now(timezone.utc)
            existing.stale_at = now
            existing.updated_at = now
            await self.db.flush()
