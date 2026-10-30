"""TRACK-C C3: 監査結果キャッシュのリグレッションテスト。

同一原稿の 2 回目以降の監査では LLM 呼び出しを 0 にし、
異なる原稿では通常通り LLM 呼び出しが行われることを検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.audit.audit_cache import AuditCache, compute_manuscript_hash


@pytest.fixture
def audit_service():
    """LLM 呼び出しを記録するモック監査サービス。"""
    service = MagicMock()
    service.screen_plot = AsyncMock(return_value=(True, "OK"))
    service.audit_ability = AsyncMock(return_value=(True, "OK", ""))
    service.audit_deai = AsyncMock(return_value=(True, "OK"))
    return service


@pytest.fixture
def cache(audit_service):
    return AuditCache(service=audit_service)


def test_compute_manuscript_hash_is_sha256():
    text = "これはテスト原稿です。"
    digest = compute_manuscript_hash(text)
    assert len(digest) == 64  # SHA-256 hex digest length
    assert compute_manuscript_hash(text) == digest  # 決定的


def test_different_manuscripts_have_different_hashes():
    assert compute_manuscript_hash("原稿A") != compute_manuscript_hash("原稿B")


def test_cache_stats_initially_zero(cache):
    stats = cache.stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["size"] == 0


@pytest.mark.asyncio
async def test_same_manuscript_second_screen_plot_skips_llm(cache, audit_service):
    """同一原稿の 2 回目の screen_plot は LLM 呼び出し 0。"""
    blueprint = "これは同じ原稿です。" * 20

    # 1 回目: キャッシュミス → LLM 呼び出し 1 回
    result1 = await cache.screen_plot(blueprint)
    assert result1 == (True, "OK")
    audit_service.screen_plot.assert_awaited_once_with(blueprint)
    assert cache.misses == 1
    assert cache.hits == 0

    # 2 回目: キャッシュヒット → LLM 呼び出し 0 回
    audit_service.screen_plot.reset_mock()
    result2 = await cache.screen_plot(blueprint)
    assert result2 == (True, "OK")
    audit_service.screen_plot.assert_not_awaited()
    assert cache.hits == 1
    assert cache.misses == 1


@pytest.mark.asyncio
async def test_different_manuscript_triggers_llm_call(cache, audit_service):
    """異なる原稿では通常通り LLM 呼び出しが行われる。"""
    blueprint_a = "原稿Aのプロット内容です。"
    blueprint_b = "原稿Bのプロット内容です。"

    await cache.screen_plot(blueprint_a)
    await cache.screen_plot(blueprint_b)

    assert audit_service.screen_plot.await_count == 2
    assert cache.misses == 2
    assert cache.hits == 0


@pytest.mark.asyncio
async def test_audit_ability_cache_hit_skips_llm(cache, audit_service):
    blueprint = "blueprint"
    settings_json = "{}"
    characters_json = "{}"

    await cache.audit_ability(blueprint, settings_json, characters_json)
    audit_service.audit_ability.assert_awaited_once_with(
        blueprint, settings_json, characters_json
    )

    audit_service.audit_ability.reset_mock()
    await cache.audit_ability(blueprint, settings_json, characters_json)
    audit_service.audit_ability.assert_not_awaited()
    assert cache.hits == 1


@pytest.mark.asyncio
async def test_audit_deai_cache_hit_skips_llm(cache, audit_service):
    content = "DeAI 監査対象の本文です。"

    await cache.audit_deai(content)
    audit_service.audit_deai.assert_awaited_once_with(content)

    audit_service.audit_deai.reset_mock()
    await cache.audit_deai(content)
    audit_service.audit_deai.assert_not_awaited()
    assert cache.hits == 1


@pytest.mark.asyncio
async def test_clear_resets_cache_and_stats(cache, audit_service):
    blueprint = "clear テスト用原稿です。"

    await cache.screen_plot(blueprint)
    assert cache.misses == 1
    assert cache.size == 1

    cache.clear()
    assert cache.stats()["hits"] == 0
    assert cache.stats()["misses"] == 0
    assert cache.size == 0

    # クリア後は再度 LLM 呼び出しが発生する
    await cache.screen_plot(blueprint)
    assert audit_service.screen_plot.await_count == 2
    assert cache.misses == 1
