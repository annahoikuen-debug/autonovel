"""静的限定モードの回帰テスト（PLAN_W6 Step 5）。"""

from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from src.services.rag_prefetch_service import RagPrefetchService  # noqa: E402


@pytest.mark.asyncio
async def test_default_is_not_static_only():
    sig = inspect.signature(RagPrefetchService.prefetch_for_episode)
    assert sig.parameters["static_only"].default is False


@pytest.mark.asyncio
async def test_static_only_marks_payload():
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 1, 1, 1, "bp")
    svc._cache["1_1"]["static"] = True
    assert (await svc.get_cached(1, 1))["static"] is True


@pytest.mark.asyncio
async def test_service_owns_a_registry():
    from src.services.prefetch.registry import PrefetchRegistry

    assert isinstance(RagPrefetchService()._registry, PrefetchRegistry)


@pytest.mark.asyncio
async def test_invalidate_still_populates_no_error():
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 3, 1, 2, "bp")
    svc.invalidate(3, 2)  # 例外_none
    assert await svc.get_cached(3, 2) is None


@pytest.mark.asyncio
async def test_stats_still_has_four_keys():
    assert set(RagPrefetchService().get_stats()) == {
        "cached_episodes",
        "pending_tasks",
        "max_size",
        "keys",
    }


@pytest.mark.asyncio
async def test_static_only_adds_static_flag_on_wiring():
    """`static_only=True` で投入したタスクは payload に `"static": True` が付く。"""
    svc = RagPrefetchService()
    await svc.prefetch_for_episode(object(), 11, 1, 1, "", static_only=True)
    await asyncio.sleep(0.05)
    payload = await svc.get_cached(11, 1)
    assert payload is not None
    assert payload["static"] is True


@pytest.mark.asyncio
async def test_default_path_has_no_static_flag():
    svc = RagPrefetchService()
    await svc.prefetch_for_episode(object(), 12, 1, 1, "")
    await asyncio.sleep(0.05)
    payload = await svc.get_cached(12, 1)
    assert payload is not None
    assert "static" not in payload


@pytest.mark.asyncio
async def test_started_task_is_tracked_in_registry():
    """ハンドルはレジストリに保持される（＝個別キャンセルできる）。"""
    svc = RagPrefetchService()
    started = asyncio.Event()

    class _SlowEngine:
        async def get_project_intelligence(self, book_id, context=""):
            started.set()
            await asyncio.sleep(3600)

    await svc.prefetch_for_episode(_SlowEngine(), 13, 1, 1, "")
    await started.wait()
    assert svc.cache_key(13, 1) in svc._registry._tasks
    await svc._registry.cancel(svc.cache_key(13, 1))
    assert svc.cache_key(13, 1) not in svc._registry._tasks
