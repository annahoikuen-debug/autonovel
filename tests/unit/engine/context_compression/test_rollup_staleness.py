"""digest 更新時の stale rollup 追従テスト (PLAN_M1 Step 14).

retake（再生成）で digest が更新されたとき、該当章・巻 rollup の
stale_at が設定され、次回保存時に再生成トリガとなることを検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.context_compression.rollup_config import RollupConfig
from src.engine.context_compression.rollup_repository import DigestRollupRepository


def _make_result(models):
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=models)
    scalars.first = MagicMock(return_value=(models[0] if models else None))
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    return result


def _make_rollup(book_id, level, start_ep, end_ep, text):
    m = MagicMock()
    m.book_id = book_id
    m.level = level
    m.start_ep = start_ep
    m.end_ep = end_ep
    m.digest_text = text
    m.stale_at = None
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


class TestRollupStaleness:
    """stale rollup のマーキングと再生成トリガをテスト。"""

    @pytest.mark.asyncio
    async def test_mark_stale_for_episode_marks_block_and_volume(self):
        """ep=3 → 章(1-10) と巻(1-50) の両方が stale になる。"""
        cfg = RollupConfig(
            rollup_enabled=True,
            episodes_per_block=10,
            blocks_per_volume=5,
        )

        block_rollup = _make_rollup(1, "block", 1, 10, "old block text")
        volume_rollup = _make_rollup(1, "volume", 1, 50, "old volume text")

        # _set_stale 内の select → scalars().first() → 既存レコード
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _make_result([block_rollup]),
                _make_result([volume_rollup]),
            ]
        )

        repo = DigestRollupRepository(db)
        await repo.mark_stale_for_episode(book_id=1, episode_num=3, cfg=cfg)

        assert block_rollup.stale_at is not None
        assert volume_rollup.stale_at is not None
        assert db.flush.await_count == 2

    @pytest.mark.asyncio
    async def test_mark_stale_no_existing_record(self):
        """該当 rollup が存在しても存在しなくても例外にならない。"""
        cfg = RollupConfig(rollup_enabled=True, episodes_per_block=10, blocks_per_volume=5)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _make_result([]),  # block: 存在しない
                _make_result([]),  # volume: 存在しない
            ]
        )
        repo = DigestRollupRepository(db)

        # 例外が発生しないこと
        await repo.mark_stale_for_episode(book_id=999, episode_num=1, cfg=cfg)
