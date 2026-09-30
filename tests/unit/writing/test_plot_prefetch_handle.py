"""投機プロットタスクのハンドルが保持されることの回帰テスト（PLAN_W6 Step 9）。"""

from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.agents.writing.episode_writer import EpisodeWriter  # noqa: E402


def test_writer_declares_task_set():
    src = inspect.getsource(EpisodeWriter.__init__)
    assert "_plot_prefetch_tasks" in src


@pytest.mark.asyncio
async def test_handle_is_kept_when_expander_returns_task():
    writer = EpisodeWriter.__new__(EpisodeWriter)
    writer._plot_prefetch_tasks = set()
    holder = {}

    class FakeExpander:
        def prefetch_next_episode_plot(self, **kw):
            holder["kw"] = kw
            return asyncio.create_task(asyncio.sleep(0))

    writer.plot_expander = FakeExpander()
    task = writer.plot_expander.prefetch_next_episode_plot(book_id=1, next_ep=2, branch_id=1)
    writer._track_plot_prefetch(task)
    assert len(holder["kw"]) == 3
    await asyncio.sleep(0.01)
    assert len(writer._plot_prefetch_tasks) == 0  # 完了後は必ず片付く


@pytest.mark.asyncio
async def test_long_running_handle_is_retained_until_done():
    writer = EpisodeWriter.__new__(EpisodeWriter)
    writer._plot_prefetch_tasks = set()
    ev = asyncio.Event()

    async def forever():
        ev.set()
        await asyncio.sleep(3600)

    task = asyncio.create_task(forever())
    writer._track_plot_prefetch(task)
    await ev.wait()
    assert task in writer._plot_prefetch_tasks  # 握り潰していない
    task.cancel()
    await asyncio.sleep(0.01)
    assert len(writer._plot_prefetch_tasks) == 0


def test_track_ignores_none():
    writer = EpisodeWriter.__new__(EpisodeWriter)
    writer._track_plot_prefetch(None)  # 例外_none
    assert getattr(writer, "_plot_prefetch_tasks", set()) == set()
