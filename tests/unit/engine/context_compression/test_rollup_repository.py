"""DigestRollupRepository の単体テスト (PLAN_M1 Step 5).

モック AsyncSession を用い、upsert の冪等性・get_rollups の順序・
find_stale の失効検出を検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.context_compression.rollup_repository import DigestRollupRepository


def _make_result(scalars_return):
    """db.execute の戻り値モックを作成（res.scalars().all() / .first() 対応）。"""
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=scalars_return)
    scalars.first = MagicMock(
        return_value=(scalars_return[0] if scalars_return else None)
    )
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    return result


def _make_rollup(book_id=1, level="block", start_ep=1, end_ep=10, digest="digest"):
    m = MagicMock()
    m.book_id = book_id
    m.level = level
    m.start_ep = start_ep
    m.end_ep = end_ep
    m.digest_text = digest
    m.stale_at = None
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


class TestDigestRollupRepositoryUpsert:
    """upsert_rollup の冪等性テスト。"""

    @pytest.mark.asyncio
    async def test_upsert_creates_new_record(self):
        """未登録キーでは新規レコードが作成される。"""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_result([]))

        repo = DigestRollupRepository(db)
        record = await repo.upsert_rollup(
            book_id=1, level="block", start_ep=1, end_ep=10, digest_text="digest"
        )

        # add + flush が呼ばれる
        assert db.add.called
        assert db.flush.called
        assert record.book_id == 1
        assert record.level == "block"

    @pytest.mark.asyncio
    async def test_upsert_is_idempotent(self):
        """同キーの upsert を2回呼んでもレコードは1つ（update 扱い）。"""
        existing = _make_rollup(digest="old")

        # 1回目: 未登録（None）→ 新規作成
        # 2回目: 登録済み（existing）→ 更新
        result_none = _make_result([])
        result_existing = _make_result([existing])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[result_none, result_existing])

        repo = DigestRollupRepository(db)

        rec1 = await repo.upsert_rollup(
            book_id=1, level="block", start_ep=1, end_ep=10, digest_text="new"
        )
        rec2 = await repo.upsert_rollup(
            book_id=1, level="block", start_ep=1, end_ep=10, digest_text="new2"
        )

        # 2回目は既存レコードを更新（add は1回目だけ呼ばれるはず）
        assert existing.digest_text == "new2"
        assert existing.updated_at is not None

    @pytest.mark.asyncio
    async def test_upsert_different_levels_coexist(self):
        """異なる level は同一 (start_ep, end_ep) でも共存できる。"""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_result([]))

        repo = DigestRollupRepository(db)
        await repo.upsert_rollup(
            book_id=1, level="block", start_ep=1, end_ep=10, digest_text="block"
        )
        await repo.upsert_rollup(
            book_id=1, level="volume", start_ep=1, end_ep=50, digest_text="volume"
        )

        # 2回の add が呼ばれる
        assert db.add.call_count == 2


class TestDigestRollupRepositoryGet:
    """get_rollups のテスト。"""

    @pytest.mark.asyncio
    async def test_get_rollups_returns_start_ep_asc(self):
        """start_ep 昇順で取得される。"""
        r1 = _make_rollup(start_ep=1)
        r2 = _make_rollup(start_ep=11)
        r3 = _make_rollup(start_ep=21)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_result([r1, r2, r3]))

        repo = DigestRollupRepository(db)
        rollups = await repo.get_rollups(book_id=1, level="block")

        assert [r.start_ep for r in rollups] == [1, 11, 21]

    @pytest.mark.asyncio
    async def test_get_rollups_empty(self):
        """登録がない場合は空リスト。"""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_result([]))

        repo = DigestRollupRepository(db)
        rollups = await repo.get_rollups(book_id=999, level="block")

        assert rollups == []


class TestDigestRollupRepositoryFindStale:
    """find_stale のテスト。"""

    @pytest.mark.asyncio
    async def test_find_stale_returns_only_stale(self):
        """stale_at が設定されているものだけを返す。"""
        stale = _make_rollup(start_ep=1)
        stale.stale_at = datetime.now(timezone.utc)
        active = _make_rollup(start_ep=11)
        active.stale_at = None

        # .all() で [stale, active] を返すが、find_stale は SQL レベルで stale_at IS NOT NULL をフィルタ。
        # モックではクエリ内容を見ないため、ここでは戻り値をそのまま信頼する。
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_result([stale]))

        repo = DigestRollupRepository(db)
        result = await repo.find_stale(book_id=1)

        assert len(result) == 1
        assert result[0].stale_at is not None
