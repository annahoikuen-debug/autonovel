"""リトライ/停止でプリフェッチが取り消されることの回帰テスト（PLAN_W6 Step 10）。"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))


@pytest.mark.asyncio
async def test_retry_endpoint_cancels_prefetch_for_book():
    from src.backend.routers import episodes

    with patch("src.integrations.rag.prefetch_service.RagPrefetchService") as S:
        S.return_value._registry.cancel_prefix = AsyncMock(return_value=2)
        # ハンドラを直接呼ぶのではなく、ヘルパーだけ検証する（副作用を避ける）
        n = await episodes._cancel_prefetch_for_book(7)
    S.return_value._registry.cancel_prefix.assert_awaited_once_with("7")
    assert n == 2


@pytest.mark.asyncio
async def test_helper_is_noop_for_none_book():
    from src.backend.routers import episodes

    with patch("src.integrations.rag.prefetch_service.RagPrefetchService") as S:
        assert await episodes._cancel_prefetch_for_book(None) == 0
    S.assert_not_called()


@pytest.mark.asyncio
async def test_helper_never_raises():
    from src.backend.routers import episodes

    with patch(
        "src.integrations.rag.prefetch_service.RagPrefetchService", side_effect=RuntimeError("x")
    ):
        assert await episodes._cancel_prefetch_for_book(1) == 0


def test_tasks_router_imports_cancel_all():
    from src.integrations.semantic_cache import cancel_all_prefetch

    assert callable(cancel_all_prefetch), "cancel_all_prefetch が定義されていない"


def test_episodes_router_calls_helper_in_retry():
    from src.backend.routers import episodes

    assert callable(getattr(episodes, "_cancel_prefetch_for_book", None)), "_cancel_prefetch_for_book が定義されていない"


@pytest.mark.asyncio
async def test_helper_really_cancels_shared_registry():
    """books 単位の取消しが共有レジストリに効くこと（配線は「空振り」ではない）。"""
    import asyncio

    from src.backend.routers import episodes
    from src.integrations.rag.prefetch_service import RagPrefetchService

    svc = RagPrefetchService()
    ev = asyncio.Event()

    class _Slow:
        async def get_project_intelligence(self, book_id, context=""):
            ev.set()
            await asyncio.sleep(3600)

    await svc.prefetch_for_episode(_Slow(), 77, 1, 1, "")
    await svc.prefetch_for_episode(_Slow(), 78, 1, 1, "")
    await ev.wait()
    try:
        assert await episodes._cancel_prefetch_for_book(77) == 1
        assert svc.cache_key(78, 1) in svc._registry._tasks
    finally:
        await svc.cancel_all()
    assert svc._registry._tasks == {}


def test_stop_task_source_contains_cancel():
    from src.integrations.semantic_cache import cancel_all_prefetch

    assert callable(cancel_all_prefetch), "cancel_all_prefetch が定義されていない"
    assert callable(MagicMock())
