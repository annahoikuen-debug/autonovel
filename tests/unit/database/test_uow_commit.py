"""UnitOfWork.commit() の実装テスト（AsyncMock に依存しない実実装検証）。

正常コミット・ロールバック・outbox 記録を SQLite の実 DB で検証する。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from src.backend.database import UnitOfWork
from src.backend.database.core import DatabaseManager


async def _setup_tables(db: DatabaseManager):
    async with db.get_session() as session:
        async with session.begin():
            await session.execute(
                text("CREATE TABLE IF NOT EXISTS uow_test (id INTEGER PRIMARY KEY, val TEXT)")
            )
            await session.execute(text("DELETE FROM uow_test"))
            await session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type VARCHAR(64) NOT NULL,
                    payload TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    processed_at DATETIME,
                    error_message TEXT
                )
            """)
            )
            await session.execute(text("DELETE FROM outbox"))


@pytest.mark.asyncio
async def test_commit_persists_sqlite_and_outbox():
    """commit() で SQLite が永続化され、outbox に 1 件記録されること。"""
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await _setup_tables(db)

    async with UnitOfWork(db) as uow:
        conn = await uow.session.connection()
        await conn.exec_driver_sql(
            "INSERT INTO uow_test (id, val) VALUES (?, ?)", (1, "hello")
        )
        uow.stage_chroma_add("test_col", "doc_uow", "uow content", [0.1, 0.2])

    # コミット後の確認（別セッションで読み取り、永続化を確認）
    async with db.get_session() as session:
        result = await session.execute(text("SELECT * FROM uow_test WHERE id=1"))
        row = result.mappings().fetchone()
        assert row is not None
        assert row["val"] == "hello"

        outbox_result = await session.execute(text("SELECT * FROM outbox"))
        outbox_rows = outbox_result.mappings().fetchall()

    assert len(outbox_rows) == 1
    assert outbox_rows[0]["event_type"] == "chroma_add"
    payload = json.loads(outbox_rows[0]["payload"])
    assert payload["id"] == "doc_uow"


@pytest.mark.asyncio
async def test_commit_rollback_on_exception():
    """例外発生時に rollback され、outbox も記録されないこと。"""
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await _setup_tables(db)

    try:
        async with UnitOfWork(db) as uow:
            conn = await uow.session.connection()
            await conn.exec_driver_sql(
                "INSERT INTO uow_test (id, val) VALUES (?, ?)", (2, "failed")
            )
            uow.stage_chroma_add("test_col", "doc_failed", "failed content", [0.1])
            raise ValueError("Forced error to trigger rollback")
    except ValueError:
        pass

    async with db.get_session() as session:
        result = await session.execute(text("SELECT * FROM uow_test WHERE id=2"))
        row = result.mappings().fetchone()
        assert row is None

        outbox_result = await session.execute(text("SELECT * FROM outbox"))
        outbox_rows = outbox_result.mappings().fetchall()

    assert len(outbox_rows) == 0
