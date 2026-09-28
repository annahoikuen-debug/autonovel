"""伏線リポジトリ（DB永続化版）の単体テスト。

v5.3 までは AsyncMock で「SELECT（現在値）→ UPDATE」の2往復を模倣し
`DbForeshadowingRepository` の各メソッドの動作を検証していた。

v5.3 Step 18/19: 遷移判定を WHERE 句に埋め込んだ CAS（単一 UPDATE）に変わったため、
往復の形をモックで固定しても実際の SQL 制約（終端巻き戻し・horizon 0）を
検証できない。そこで遷移系は **実 async SQLite（aiosqlite）** で検証する。
読み取り専用の検索・集計系は従来どおりモックで外形を固定する。
"""
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, MagicMock

from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository


def _tables_with_fk_closure(table) -> list:
    """対象テーブルと、その外部キーが参照するテーブルを推移的に集める。

    SQLite は `PRAGMA foreign_keys=ON` のとき、参照先テーブルが存在しないと
    INSERT 自体を拒否する。伏線1行のテストのためにbooks→tenants…と
    全部作るのは重すぎるので、必要なテーブルだけを集める。
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
async def create_test_db(url: str = "sqlite+aiosqlite:///:memory:"):
    """伏線テーブルと FK 先のテーブルを、実 async SQLite（aiosqlite）上に用意する。"""
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_tables_with_fk_closure(ForeshadowingModel.__table__),
        )
        # 親行が無いと FK 制約で INSERT が弾かれるので最低限の行を1件置く
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


async def _plant(session_factory, **kwargs):
    """伏線を1本設置し、その id を返す"""
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


@pytest.mark.asyncio
async def test_foreshadowing_repo_get_unresolved():
    """未回収伏線の取得を検証"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_foreshadowing = MagicMock(id=1, title="謎の剣", status="planted", planted_episode=3)
    mock_result.scalars.return_value.all.return_value = [mock_foreshadowing]
    mock_db.execute.return_value = mock_result

    repo = DbForeshadowingRepository(mock_db)
    items = await repo.get_unresolved(book_id=1)

    assert len(items) == 1
    assert items[0].title == "謎の剣"
    assert items[0].status == "planted"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_foreshadowing_repo_add():
    """伏線の新規設置を検証"""
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()

    repo = DbForeshadowingRepository(mock_db)
    result = await repo.add(
        book_id=1,
        title="消えた手紙",
        description="第5話で主人公が見つけた手紙が突然消えた",
        planted_episode=5,
        target_episode=12,
    )

    assert result.title == "消えた手紙"
    assert result.planted_episode == 5
    assert result.status == "planted"
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_foreshadowing_repo_resolve():
    """伏線の回収更新を検証（planted → resolved）"""
    async with create_test_db() as sf:
        f_id = await _plant(sf)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(foreshadowing_id=f_id, episode_num=10) is True
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "resolved"
            assert row.resolved_episode == 10


@pytest.mark.asyncio
async def test_foreshadowing_repo_resolve_not_found():
    """存在しない伏線の回収は False を返す"""
    async with create_test_db() as sf:
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(foreshadowing_id=9999, episode_num=10) is False


@pytest.mark.asyncio
async def test_foreshadowing_repo_resolve_rejects_terminal_rollback():
    """終端状態（resolved）からの巻き戻しは拒否され、値が保持される"""
    async with create_test_db() as sf:
        f_id = await _plant(sf)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(f_id, 10) is True
            await session.commit()
            # resolved は終端状態（sink）なので resolved へも遷移できない
            assert await repo.resolve(f_id, 11) is False
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.resolved_episode == 10, "終端状態から巻き戻っている"


@pytest.mark.asyncio
async def test_foreshadowing_repo_resolve_rejects_before_plant_episode():
    """設置话より前の话での回収は不変条件違反として拒否する"""
    async with create_test_db() as sf:
        f_id = await _plant(sf, planted_episode=5)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(foreshadowing_id=f_id, episode_num=3) is False
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "planted"
            assert row.resolved_episode is None


@pytest.mark.asyncio
async def test_foreshadowing_repo_resolve_allows_same_episode_as_plant():
    """境界: 設置話と同時回収（resolved == planted）は不変条件上は許可される"""
    async with create_test_db() as sf:
        f_id = await _plant(sf, planted_episode=5)
        async with sf() as session:
            assert await DbForeshadowingRepository(session).resolve(f_id, 5) is True


@pytest.mark.asyncio
async def test_foreshadowing_repo_progress_allows_from_planted():
    """planted → progressed は許可される"""
    async with create_test_db() as sf:
        f_id = await _plant(sf)
        async with sf() as session:
            assert await DbForeshadowingRepository(session).progress(foreshadowing_id=f_id) is True


@pytest.mark.asyncio
async def test_foreshadowing_repo_progress_rejects_self_transition():
    """progressed → progressed は許可されない（誤った再更新の防止）"""
    async with create_test_db() as sf:
        f_id = await _plant(sf)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.progress(f_id) is True
            assert await repo.progress(f_id) is False


@pytest.mark.asyncio
async def test_foreshadowing_repo_progress_rejects_after_resolve():
    """解決済み伏線を progressed へ巻き戻さない（CAS 化の中核回帰）"""
    async with create_test_db() as sf:
        f_id = await _plant(sf)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(f_id, 10) is True
            await session.commit()
            assert await repo.progress(f_id) is False
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "resolved"


@pytest.mark.asyncio
async def test_foreshadowing_repo_abandon_from_progressed():
    """progressed → abandoned は許可される"""
    async with create_test_db() as sf:
        f_id = await _plant(sf)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.progress(f_id) is True
            assert await repo.abandon(f_id) is True
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "abandoned"


@pytest.mark.asyncio
async def test_foreshadowing_repo_unknown_status_passes_through():
    """判断D2: 未知ステータス（手動投入・旧データ）はガード対象外＝素通し"""
    async with create_test_db() as sf:
        f_id = await _plant(sf)
        async with sf() as session:
            await session.execute(
                ForeshadowingModel.__table__.update()
                .where(ForeshadowingModel.id == f_id)
                .values(status="legacy_unknown")
            )
            await session.commit()

        async with sf() as session:
            assert await DbForeshadowingRepository(session).progress(f_id) is True
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.status == "progressed"


@pytest.mark.asyncio
async def test_foreshadowing_repo_update_target_episode():
    """v5.3: Rescheduler が実際に呼べる延期 API が存在する"""
    async with create_test_db() as sf:
        f_id = await _plant(sf, planted_episode=3)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.update_target_episode(foreshadowing_id=f_id, target_episode=12) is True
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.target_episode == 12


@pytest.mark.asyncio
async def test_foreshadowing_repo_update_target_episode_rejects_terminal():
    """終端状態の伏線は延期しない"""
    async with create_test_db() as sf:
        f_id = await _plant(sf, planted_episode=3)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.resolve(f_id, 10) is True
            await session.commit()
            assert await repo.update_target_episode(f_id, 12) is False
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.target_episode == 8, "終端状態の伏線が延期された"


@pytest.mark.asyncio
async def test_foreshadowing_repo_update_target_episode_rejects_before_plant():
    """設置話より前の回収予定は設定しない"""
    async with create_test_db() as sf:
        f_id = await _plant(sf, planted_episode=8)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.update_target_episode(foreshadowing_id=f_id, target_episode=4) is False
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.target_episode == 8


@pytest.mark.asyncio
async def test_foreshadowing_repo_update_target_episode_rejects_horizon_zero():
    """境界: target == planted（horizon 0）は planner の不変条件と不整合するため拒否する"""
    async with create_test_db() as sf:
        f_id = await _plant(sf, planted_episode=8)
        async with sf() as session:
            repo = DbForeshadowingRepository(session)
            assert await repo.update_target_episode(foreshadowing_id=f_id, target_episode=8) is False
            # 1话後なら許可される
            assert await repo.update_target_episode(foreshadowing_id=f_id, target_episode=9) is True
            await session.commit()

        async with sf() as session:
            row = await DbForeshadowingRepository(session).get_by_id(f_id)
            assert row.target_episode == 9


@pytest.mark.asyncio
async def test_foreshadowing_repo_horizon_zero_rejection_is_counted():
    """horizon 0 の拒否はメトリクスに記録される（観測可能性）"""
    from src.backend.observability import metrics as m

    before = m.foreshadowing_transitions_rejected_total.labels(reason="horizon_zero")._value.get()
    async with create_test_db() as sf:
        f_id = await _plant(sf, planted_episode=8)
        async with sf() as session:
            assert await DbForeshadowingRepository(session).update_target_episode(f_id, 8) is False
    after = m.foreshadowing_transitions_rejected_total.labels(reason="horizon_zero")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_foreshadowing_repo_get_balance():
    """伏線バランス集計を検証"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        ("planted", 5),
        ("progressed", 2),
        ("resolved", 3),
    ]
    mock_db.execute.return_value = mock_result

    repo = DbForeshadowingRepository(mock_db)
    balance = await repo.get_balance(book_id=1)

    assert balance["planted"] == 5
    assert balance["progressed"] == 2
    assert balance["resolved"] == 3
    assert balance["abandoned"] == 0
    assert balance["active"] == 7  # planted + progressed


@pytest.mark.asyncio
async def test_foreshadowing_repo_get_overdue():
    """期限超過伏線の取得を検証"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    overdue = MagicMock(id=2, title="忘れられた約束", status="planted", target_episode=8)
    mock_result.scalars.return_value.all.return_value = [overdue]
    mock_db.execute.return_value = mock_result

    repo = DbForeshadowingRepository(mock_db)
    items = await repo.get_overdue(book_id=1, current_episode=12)

    assert len(items) == 1
    assert items[0].title == "忘れられた約束"
