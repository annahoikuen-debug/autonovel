"""ReflectiveRAGService 永続化の回帰防止テスト。

同期/非同期の境界が厳密化されていること（nest_asyncio / asyncio.run に依存しない）
および DB 障害時にフローを阻害しないことを検証する。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.rag.reflective_rag import ReflectiveRAGService, ReflectiveRetrievalResult


def _make_result() -> ReflectiveRetrievalResult:
    return ReflectiveRetrievalResult(
        original_query="テストクエリ",
        documents=[],
        iterations=2,
        initial_doc_count=10,
        final_doc_count=5,
        converged=True,
        refined_queries=["テストクエリ refined"],
    )


@pytest.mark.asyncio
async def test_save_reflection_history_async_persists_and_commits():
    svc = ReflectiveRAGService.__new__(ReflectiveRAGService)
    session = AsyncMock()
    await svc.save_reflection_history_async(session, _make_result(), book_id=1)
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_reflection_history_async_no_session_is_noop():
    svc = ReflectiveRAGService.__new__(ReflectiveRAGService)
    # None セッションでも例外を出さない
    await svc.save_reflection_history_async(None, _make_result())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_save_reflection_history_async_db_error_does_not_raise(caplog):
    svc = ReflectiveRAGService.__new__(ReflectiveRAGService)
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("db down")
    # 例外が外部にリークしない
    await svc.save_reflection_history_async(session, _make_result())
    assert any("Failed to persist" in r.message for r in caplog.records)


def test_save_reflection_history_sync_session_persists():
    svc = ReflectiveRAGService.__new__(ReflectiveRAGService)
    session = MagicMock(spec=[])  # run_sync を持たない純粋な同期セッション
    session.execute = MagicMock(return_value=MagicMock())
    session.commit = MagicMock()
    svc.save_reflection_history(session, _make_result(), book_id=1)
    session.execute.assert_called_once()
    session.commit.assert_called_once()


def test_save_reflection_history_async_session_is_skipped():
    """非同期セッションが渡された場合は例外を出さず安全にスキップする。"""
    svc = ReflectiveRAGService.__new__(ReflectiveRAGService)
    session = MagicMock()
    session.run_sync = MagicMock()  # AsyncSession 特徴の検出用
    coro_inst = None

    async def _coro(*args: Any, **kwargs: Any):
        return None

    coro_inst = _coro()
    session.execute.return_value = coro_inst
    # 例外が出ず、asyncio.run も呼ばれないことを確認
    svc.save_reflection_history(session, _make_result())
    session.commit.assert_not_called()
    coro_inst.close()


def test_save_reflection_history_sync_db_error_does_not_raise():
    svc = ReflectiveRAGService.__new__(ReflectiveRAGService)
    session = MagicMock()
    session.execute.side_effect = RuntimeError("db down")
    svc.save_reflection_history(session, _make_result())


def test_no_nest_asyncio_dependency():
    """reflective_rag モジュールが nest_asyncio に依存していないこと。"""
    import inspect as _inspect

    import src.services.rag.reflective_rag as mod

    source = _inspect.getsource(mod)
    assert "import nest_asyncio" not in source
    assert "nest_asyncio.apply" not in source
    # 実行コード中の asyncio.run 呼び出しがないこと（docstring 記載は許容）
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "run" or not _is_asyncio(node.func.value)


def _is_asyncio(node: Any) -> bool:
    return isinstance(node, __import__("ast").Name) and node.id == "asyncio"
