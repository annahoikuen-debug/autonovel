import pytest
from unittest.mock import AsyncMock, MagicMock
from src.backend.database.repositories.chapter import ChapterRepository
from src.backend.database.models import Chapter

def _sql_of(mock_session) -> str:
    """実行されたステートメントの SQL 文字列を取り出す。

    呼び出し回数だけを検証しても、WHERE 句が落thropdownarrowしていても通ってしまう。
    「book_id でスコープされているか」を検証するのがこのファイルの意義なので、
    SQL を直接見てbook_id の述語を確かめる。
    """
    stmt = mock_session.execute.await_args[0][0]
    return str(stmt)

@pytest.mark.asyncio
async def test_chapter_update_content():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(rowcount=1))

    repo = ChapterRepository(mock_session)
    updated = await repo.update_chapter_content(
        branch_id=1, ep_num=1, content="新しい本文（15文字）", book_id=7
    )

    mock_session.execute.assert_awaited_once()
    assert updated == 1
    sql = _sql_of(mock_session)
    assert "book_id" in sql, f"book_id でスコープされていない: {sql}"
    assert "chapters.ep_num" in sql

@pytest.mark.asyncio
async def test_chapter_update_content_without_book_id_stays_branch_scoped():
    """book_id 未指定は後方互換のため残す（内部の執筆フロー用）。"""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(rowcount=1))

    repo = ChapterRepository(mock_session)
    await repo.update_chapter_content(branch_id=1, ep_num=1, content="x")

    sql = _sql_of(mock_session)
    assert "book_id" not in sql

@pytest.mark.asyncio
async def test_chapter_create_new():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()

    repo = ChapterRepository(mock_session)
    await repo.create_chapter(
        book_id=1,
        ep_num=1,
        title="Chapter 1",
        content="First chapter content",
        summary="Summary 1",
        killer_phrase="Phrase",
        ai_insight="Insight",
        world_state={"weather": "sunny"},
        trinity_review_log={},
        created_at="2026-09-15T00:00:00",
        branch_id=1,
    )

    mock_session.add.assert_called_once()
    created = mock_session.add.call_args[0][0]
    assert created.book_id == 1
    assert created.branch_id == 1
    assert created.ep_num == 1
    # 照合クエリは (book_id, branch_id, ep_num) の 3 キーでなければならない
    sql = _sql_of(mock_session)
    for col in ("book_id", "branch_id", "ep_num"):
        assert f"chapters.{col}" in sql, f"照合に {col} が含まれていない: {sql}"

@pytest.mark.asyncio
async def test_chapter_get():
    mock_session = AsyncMock()
    mock_chapter = Chapter(
        id=1,
        book_id=1,
        branch_id=1,
        ep_num=1,
        title="Chapter 1",
        content="Content 1",
        summary="Chapter 1 plain summary",
        world_state="{}",
        trinity_review_log="{}",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_chapter
    mock_session.execute.return_value = mock_result

    repo = ChapterRepository(mock_session)
    ch = await repo.get_chapter(branch_id=1, ep_num=1)
    assert ch is not None
    assert ch.title == "Chapter 1"

@pytest.mark.asyncio
async def test_chapter_get_none():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    repo = ChapterRepository(mock_session)
    ch = await repo.get_chapter(branch_id=1, ep_num=99)
    assert ch is None

@pytest.mark.asyncio
async def test_chapter_delete():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(rowcount=1))

    repo = ChapterRepository(mock_session)
    deleted = await repo.delete_chapter(1, 1)

    mock_session.execute.assert_awaited_once()
    assert deleted == 1
    sql = _sql_of(mock_session)
    for col in ("book_id", "branch_id", "ep_num"):
        assert f"chapters.{col}" in sql, f"削除条件に {col} が含まれていない: {sql}"

@pytest.mark.asyncio
async def test_chapter_delete_reports_zero_when_absent():
    """対象が無いときに 0 を返し、呼び出し側が 404 にできる。"""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(rowcount=0))

    repo = ChapterRepository(mock_session)
    assert await repo.delete_chapter(1, 999) == 0
