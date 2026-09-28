"""v5.3 伏線ステートマシンの原子性リグジェーションテスト（Step 20）。

`_transition` / `update_target_episode` は v5.3 Step 18/19 まで
「SELECT（現在値）→ 判定 → WHERE 条件なし UPDATE」という2往復で実装されており、
並行実行すると「回収済み(resolved) 行が progressed へ巻き戻る」事故が起こり得た。

本テストはモックではなく **実 async SQLite（aiosqlite）** を使い、
2セッションが競合する状況を再現して巻き戻しがゼロであることを証明する。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository


def _tables_with_fk_closure(table) -> list:
    """対象テーブルと、その外部キーが参照するテーブルを推移的に集める。

    SQLite は `PRAGMA foreign_keys=ON` のとき参照先テーブルが無いと INSERT を拒否する。
    伏線1行のテストのために books→tenants… と全部作るのは重すぎるので必要な物だけ集める。
    """
    collected: list = []
    stack = [table]
    while stack:
        current = stack.pop()
        if current in collected:
            continue
        collected.append(current)
        for fk in current.foreign_keys:
            stack.append(fk.column.table)
    return collected


@asynccontextmanager
async def _shared_file_db(tmp_path):
    """2セッションから同時アクセスできる実 SQLite ファイルを用意する。

    インメモリ DB は接続ごとに別 DB になるため、並行性の検証には使えない。
    `timeout=10` でロック待ちを持ち、"database is locked" によるフレークを防ぐ。
    """
    db_path = tmp_path / "concurrent_foreshadowing.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", echo=False, connect_args={"timeout": 10}
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_tables_with_fk_closure(ForeshadowingModel.__table__),
        )
        for table in _tables_with_fk_closure(ForeshadowingModel.__table__):
            if table.name == "books":
                await conn.execute(
                    insert(table).values(
                        id=1,
                        title="テスト作品",
                        mode="easy",
                        genre="",
                        concept="",
                        synopsis="",
                        catchcopy="",
                        style_dna="",
                        status="draft",
                        marketing_data="",
                    )
                )
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        yield session_factory
    finally:
        await engine.dispose()


async def _plant(session_factory, **kwargs) -> int:
    params = {
        "book_id": 1,
        "title": "謎の剣",
        "description": "d",
        "planted_episode": 3,
        "target_episode": 8,
    }
    params.update(kwargs)
    async with session_factory() as session:
        record = await DbForeshadowingRepository(session).add(**params)
        await session.commit()
        return record.id


# ── テスト1: resolve と progress の競合で巻き戻らない ─────────────


@pytest.mark.asyncio
async def test_concurrent_resolve_and_progress_does_not_rollback(tmp_path):
    """A が resolved した後、B の progress は rowcount=0 で拒否され、巻き戻らない"""
    async with _shared_file_db(tmp_path) as sf:
        f_id = await _plant(sf)

        # セッションA: 回収する
        async with sf() as session_a:
            repo_a = DbForeshadowingRepository(session_a)
            assert await repo_a.resolve(f_id, 10) is True
            await session_a.commit()

        # セッションB: 別セッションから進捗更新を試みる（CAS により拒否される）
        async with sf() as session_b:
            repo_b = DbForeshadowingRepository(session_b)
            assert await repo_b.progress(f_id) is False
            await session_b.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "resolved", "解決済み伏線が progressed へ巻き戻った"
            assert row.resolved_episode == 10


@pytest.mark.asyncio
async def test_concurrent_resolve_and_progress_gathered(tmp_path):
    """2セッションを実際に並行実行しても、最終状態は resolved のまま"""
    async with _shared_file_db(tmp_path) as sf:
        f_id = await _plant(sf)

        async def _resolve() -> bool:
            async with sf() as session:
                ok = await DbForeshadowingRepository(session).resolve(f_id, 12)
                await session.commit()
                return ok

        async def _progress() -> bool:
            async with sf() as session:
                ok = await DbForeshadowingRepository(session).progress(f_id)
                await session.commit()
                return ok

        results = await asyncio.gather(_resolve(), _progress())

        # どちらかが必ず成功し、もう一方は拒否される（両方が成功してはいけない）
        assert sorted(results) == [False, True], f"CAS が機能していない: {results}"

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "resolved"
            assert row.resolved_episode == 12


@pytest.mark.asyncio
async def test_concurrent_double_progress_second_is_rejected(tmp_path):
    """同時に2回 progressed へ遷移させても、2回目はガードで拒否される"""
    async with _shared_file_db(tmp_path) as sf:
        f_id = await _plant(sf)

        async def _progress() -> bool:
            async with sf() as session:
                ok = await DbForeshadowingRepository(session).progress(f_id)
                await session.commit()
                return ok

        results = await asyncio.gather(_progress(), _progress())
        assert results.count(True) == 1, f"progressed → progressed が許容された: {results}"


# ── テスト2: 回収済み行が get_unresolved に混ざらない ─────────────


@pytest.mark.asyncio
async def test_resolved_row_never_reenters_get_unresolved(tmp_path):
    """並行実行の後も、回収済み行は未回収検索に戻ってこない"""
    async with _shared_file_db(tmp_path) as sf:
        active_id = await _plant(sf, title="残される伏線")
        done_id = await _plant(sf, title="回収される伏線", planted_episode=4)

        async def _resolve() -> bool:
            async with sf() as session:
                ok = await DbForeshadowingRepository(session).resolve(done_id, 9)
                await session.commit()
                return ok

        async def _progress() -> bool:
            async with sf() as session:
                ok = await DbForeshadowingRepository(session).progress(active_id)
                await session.commit()
                return ok

        await asyncio.gather(_resolve(), _progress())

        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            unresolved = await repo.get_unresolved(1)
            ids = [f.id for f in unresolved]
            assert done_id not in ids, "回収済み行が get_unresolved に混ざった"
            assert active_id in ids
            assert all(f.status in ("planted", "progressed") for f in unresolved)


@pytest.mark.asyncio
async def test_resolved_row_is_excluded_even_after_rollback_attempt(tmp_path):
    """巻き戻し試行の後も、回収済み行は未回収一覧から消えたまま"""
    async with _shared_file_db(tmp_path) as sf:
        f_id = await _plant(sf)

        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(f_id, 9) is True
            await session.commit()
            assert await repo.progress(f_id) is False
            assert await repo.abandon(f_id) is False
            await session.commit()

        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.get_unresolved(1) == []
            assert await repo.update_target_episode(f_id, 20) is False
            await session.commit()


# ── テスト3: 拒否がメトリクスに記録される ───────────────────────


@pytest.mark.asyncio
async def test_transition_rejection_is_counted(tmp_path):
    """拒否は `foreshadowing_transitions_rejected_total` に記録される"""
    from src.backend.observability import metrics as m

    metric = m.foreshadowing_transitions_rejected_total
    before = {reason: metric.labels(reason=reason)._value.get() for reason in ("illegal_transition", "horizon_zero")}

    async with _shared_file_db(tmp_path) as sf:
        f_id = await _plant(sf, planted_episode=8)

        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            # 回収済みへの巻き戻し（terminal）→ 拒否
            assert await repo.resolve(f_id, 10) is True
            await session.commit()
            assert await repo.progress(f_id) is False
            # horizon 0 の延期 → 拒否
            assert await repo.update_target_episode(f_id, 8) is False
            await session.commit()

    after = {reason: metric.labels(reason=reason)._value.get() for reason in before}
    assert after["illegal_transition"] == before["illegal_transition"] + 1
    assert after["horizon_zero"] == before["horizon_zero"] + 1


@pytest.mark.asyncio
async def test_concurrent_reschedule_and_resolve_does_not_reopen(tmp_path):
    """延期と回収が同時に走っても、終端状態の伏線が active へ戻らない"""
    async with _shared_file_db(tmp_path) as sf:
        f_id = await _plant(sf, planted_episode=3, target_episode=8)

        async def _resolve() -> bool:
            async with sf() as session:
                ok = await DbForeshadowingRepository(session).resolve(f_id, 20)
                await session.commit()
                return ok

        async def _reschedule() -> bool:
            async with sf() as session:
                ok = await DbForeshadowingRepository(session).update_target_episode(f_id, 25)
                await session.commit()
                return ok

        await asyncio.gather(_resolve(), _reschedule())

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "resolved", "終端状態の伏線が active へ戻された"
            assert await DbForeshadowingRepository(session).get_unresolved(1) == []
