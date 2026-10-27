"""`asyncio.coroutine` 依存を撤去し、engine 不在でも完走することの回帰テスト（PLAN_W6 Step 3）。"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from src.services.rag_prefetch_service import (  # noqa: E402
    RagPrefetchService,
    _null,
)


@pytest.mark.asyncio
async def test_null_helper_returns_value():
    assert await _null([]) == []
    assert await _null("") == ""
    assert await _null({}) == {}


@pytest.mark.asyncio
async def test_module_has_no_asyncio_coroutine_attribute():
    import src.services.rag_prefetch_service as mod

    assert not hasattr(mod.asyncio, "coroutine"), "Python 3.14 では削除済み"


@pytest.mark.asyncio
async def test_bare_engine_completes_without_exception():
    """engine に何も無くても例外を投げないこと（＝プリフェッチが恒久 no-op にならないこと）。"""
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 1, 1, 1, "blueprint")
    assert await svc.get_cached(1, 1) is not None  # 空結果で必ずキャッシュされる


@pytest.mark.asyncio
async def test_bare_object_engine_completes_without_exception():
    """属性を一切持たないオブジェクトでも 3 路とも no-op コルーチンで埋まる。"""
    svc = RagPrefetchService()
    await svc._do_prefetch(object(), 4, 1, 1, "blueprint")
    payload = await svc.get_cached(4, 1)
    assert payload is not None
    assert payload["style_samples"] == []
    assert payload["rag_context"] == ""
    assert payload["intelligence"] == {}


@pytest.mark.asyncio
async def test_cache_payload_shape_unchanged():
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 2, 1, 5, "bp")
    payload = await svc.get_cached(2, 5)
    assert set(payload) == {"style_samples", "rag_context", "intelligence", "prefetched"}
    assert payload["prefetched"] is True
