"""ProviderFailoverManager の単体テスト。"""

from __future__ import annotations

import pytest

from src.services.llm.circuit_breaker import CircuitBreakerOpenException
from src.services.llm.provider_failover import ProviderFailoverManager


@pytest.mark.asyncio
async def test_primary_success_returns_primary_result():
    """プライマリが成功すればプライマリの結果とプロバイダ名を返す。"""
    mgr = ProviderFailoverManager()

    async def primary():
        return "primary-data"

    async def fallback():
        return "fallback-data"

    result, provider = await mgr.execute_with_fallback(
        "gemini", "openai", primary, fallback
    )

    assert result == "primary-data"
    assert provider == "gemini"


@pytest.mark.asyncio
async def test_primary_failure_falls_back_to_fallback():
    """プライマリが失敗すればフォールバックを実行しその結果を返す。"""
    mgr = ProviderFailoverManager()
    fallback_calls = 0

    async def primary():
        raise RuntimeError("primary down")

    async def fallback():
        nonlocal fallback_calls
        fallback_calls += 1
        return "fallback-data"

    result, provider = await mgr.execute_with_fallback(
        "gemini", "openai", primary, fallback
    )

    assert result == "fallback-data"
    assert provider == "openai"
    assert fallback_calls == 1


@pytest.mark.asyncio
async def test_both_breakers_open_raises_circuit_breaker_open():
    """プライマリとフォールバックの両方が遮断されていれば例外を送出する。"""
    mgr = ProviderFailoverManager()

    # ブレーカーを OPEN にする（failure_threshold=3 回の失敗が必要）
    async def failing_fn():
        raise RuntimeError("boom")

    for _ in range(3):
        try:
            await mgr.execute_with_fallback("gemini", "openai", failing_fn, failing_fn)
        except (RuntimeError, CircuitBreakerOpenException):
            pass

    async def primary():
        return "primary-data"

    async def fallback():
        return "fallback-data"

    with pytest.raises(CircuitBreakerOpenException):
        await mgr.execute_with_fallback("gemini", "openai", primary, fallback)


@pytest.mark.asyncio
async def test_unknown_provider_has_no_breaker():
    """未登録プロバイダーはブレーカーなしとして扱われる。"""
    mgr = ProviderFailoverManager()

    async def primary():
        return "unknown-primary"

    async def fallback():
        return "fallback-data"

    result, provider = await mgr.execute_with_fallback(
        "unknown-provider", "openai", primary, fallback
    )

    assert result == "unknown-primary"
    assert provider == "unknown-provider"


@pytest.mark.asyncio
async def test_primary_breaker_open_skips_primary():
    """プライマリブレーカーが OPEN ならプライマリをスキップしフォールバックを実行する。"""
    mgr = ProviderFailoverManager()

    # プライマリのブレーカーだけを OPEN にする（failure_threshold=3 回の失敗）。
    # CircuitBreaker は provider_name="default" で初期化されるため、
    # record_failure()/can_execute() は引数なし（"default" キー）で呼ぶ。
    primary_breaker = mgr.breakers["gemini"]
    for _ in range(3):
        primary_breaker.record_failure()

    # can_execute が False になっていることを確認
    assert not primary_breaker.can_execute()

    primary_called = False

    async def primary():
        nonlocal primary_called
        primary_called = True
        return "should-not-run"

    async def fallback():
        return "fallback-data"

    result, provider = await mgr.execute_with_fallback(
        "gemini", "openai", primary, fallback
    )

    assert not primary_called
    assert result == "fallback-data"
    assert provider == "openai"
