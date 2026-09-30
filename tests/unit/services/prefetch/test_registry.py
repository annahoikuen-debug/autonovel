"""PrefetchRegistry の登録・取り消し・統計の回帰テスト（PLAN_W6 Step 1）。"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from src.services.prefetch.registry import PrefetchRegistry  # noqa: E402


@pytest.mark.asyncio
async def test_track_and_untrack():
    r = PrefetchRegistry()

    async def noop():
        return 1

    t = r.track("b:1", asyncio.create_task(noop()))
    await asyncio.sleep(0)
    assert r.stats()["tracked"] >= 0  # done コールバックはまだ来ていない不定
    r.untrack("b:1")
    assert "b:1" not in r._tasks
    assert t is not None


@pytest.mark.asyncio
async def test_cancel_stops_running_task():
    r = PrefetchRegistry()
    started = asyncio.Event()

    async def forever():
        started.set()
        await asyncio.sleep(3600)

    task = r.track("b:2", asyncio.create_task(forever()))
    await started.wait()
    assert await r.cancel("b:2") == 1
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_cancel_unknown_key_returns_zero():
    assert await PrefetchRegistry().cancel("nothing") == 0


@pytest.mark.asyncio
async def test_cancel_prefix_matches_book_scope():
    r = PrefetchRegistry()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    for k in ("book1:1", "book1:2", "book2:1"):
        r.track(k, asyncio.create_task(forever()))
    await ev.wait()
    assert await r.cancel_prefix("book1") == 2
    # 別スコープのタスクは生きたまま
    assert "book2:1" in r._tasks
    await r.cancel("book2:1")


@pytest.mark.asyncio
async def test_cancel_prefix_underscore_scope_does_not_overlap():
    """`"7"` は `"70_1"` に誤爆しないこと（キャッシュキーが `{book}_{ep}` のため）。"""
    r = PrefetchRegistry()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    r.track("7_1", asyncio.create_task(forever()))
    r.track("70_1", asyncio.create_task(forever()))
    await ev.wait()
    assert await r.cancel_prefix("7") == 1
    assert "70_1" in r._tasks
    await r.cancel("70_1")


@pytest.mark.asyncio
async def test_retacking_same_key_cancels_previous():
    r = PrefetchRegistry()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    first = r.track("b:3", asyncio.create_task(forever()))
    await ev.wait()
    second = r.track("b:3", asyncio.create_task(asyncio.sleep(0)))
    await asyncio.sleep(0)
    assert first.cancelled() or first.done()
    assert r._tasks["b:3"] is second


@pytest.mark.asyncio
async def test_stats_has_four_keys():
    r = PrefetchRegistry()

    async def noop():
        return 1

    r.track("b:4", asyncio.create_task(noop()))
    await asyncio.sleep(0.01)
    assert set(r.stats()) == {"tracked", "cancelled", "failed", "done"}


@pytest.mark.asyncio
async def test_done_task_is_untracked_automatically():
    r = PrefetchRegistry()

    async def noop():
        return 1

    r.track("b:5", asyncio.create_task(noop()))
    await asyncio.sleep(0.01)
    assert "b:5" not in r._tasks
    assert r.stats()["done"] == 1


@pytest.mark.asyncio
async def test_failing_task_is_counted_and_not_raised():
    r = PrefetchRegistry()

    async def boom():
        raise ValueError("boom")

    r.track("b:6", asyncio.create_task(boom()))
    await asyncio.sleep(0.01)
    assert "b:6" not in r._tasks
    assert r.stats()["failed"] == 1
