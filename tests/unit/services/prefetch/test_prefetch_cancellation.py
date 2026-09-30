"""cancel_all / close がバックグラウンドタスクを確実に殺すことの回帰テスト（PLAN_W6 Step 6）。"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from src.services import semantic_cache as sc  # noqa: E402
from src.services.rag_prefetch_service import RagPrefetchService  # noqa: E402


@pytest.mark.asyncio
async def test_semantic_cancel_all_kills_tasks():
    sc._BACKGROUND_TASKS.clear()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    tasks = []
    for _ in range(3):
        t = asyncio.create_task(forever())
        sc._BACKGROUND_TASKS.add(t)
        tasks.append(t)
    await ev.wait()
    assert await sc.cancel_all_prefetch() == 3
    assert len(sc._BACKGROUND_TASKS) == 0
    assert all(t.cancelled() or t.done() for t in tasks)


@pytest.mark.asyncio
async def test_semantic_close_is_alias():
    sc._BACKGROUND_TASKS.clear()
    assert await sc.close_background_tasks() == 0
    assert len(sc._BACKGROUND_TASKS) == 0


@pytest.mark.asyncio
async def test_rag_prefetch_cancel_all():
    svc = RagPrefetchService()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    tasks = []
    for ep in (1, 2, 3):
        t = asyncio.create_task(forever())
        svc._pending_tasks[svc.cache_key(9, ep)] = t
        tasks.append(t)
    await ev.wait()
    assert await svc.cancel_all() == 3
    assert all(t.cancelled() or t.done() for t in tasks)
    assert svc._pending_tasks == {}


@pytest.mark.asyncio
async def test_rag_prefetch_close_clears_cache():
    svc = RagPrefetchService()
    svc._cache[svc.cache_key(9, 1)] = {"prefetched": True}
    await svc.close()
    assert svc._cache == {}


@pytest.mark.asyncio
async def test_cancel_all_on_empty_registry_is_zero():
    sc._BACKGROUND_TASKS.clear()
    assert await sc.cancel_all_prefetch() == 0
    assert await RagPrefetchService().cancel_all() == 0


@pytest.mark.asyncio
async def test_rag_prefetch_cancel_all_clears_registry_handles():
    """`cancel_all` はレジストリ側のハンドルも外す（＝再取り消しで二重計上されない）。"""
    svc = RagPrefetchService()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    await svc.prefetch_for_episode(_SlowEngine(ev), 21, 1, 1, "")
    await ev.wait()
    assert svc.cache_key(21, 1) in svc._registry._tasks
    assert await svc.cancel_all() == 1
    assert svc.cache_key(21, 1) not in svc._registry._tasks


@pytest.mark.asyncio
async def test_rag_prefetch_cancel_book_scopes_to_one_book():
    """書籍単位の取り消し（Step 10 の入口）。"""
    svc = RagPrefetchService()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    await svc.prefetch_for_episode(_SlowEngine(ev), 31, 1, 1, "")
    await svc.prefetch_for_episode(_SlowEngine(ev), 32, 1, 1, "")
    await ev.wait()
    assert await svc.cancel_book(31) == 1
    assert svc.cache_key(32, 1) in svc._registry._tasks
    await svc.cancel_all()


class _SlowEngine:
    """`get_project_intelligence` だけを持つ、改造した engine。"""

    def __init__(self, ev: asyncio.Event) -> None:
        self._ev = ev

    async def get_project_intelligence(self, book_id, context=""):
        self._ev.set()
        await asyncio.sleep(3600)
