"""リトライヘルパーのユニットテスト。"""
from __future__ import annotations

import pytest

from src.services.llm.retry import with_retry


async def _success_func():
    return "success"


async def _fail_func():
    raise ValueError("always fails")


async def test_with_retry_success():
    """リトライなしで成功する。"""
    result = await with_retry(_success_func, max_retries=1)
    assert result == "success"


async def test_with_retry_eventual_success():
    """リトライの末尾で成功する（2回失敗して3回目で成功）。"""
    call_count = 0

    async def eventual_success():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("temporary failure")
        return "success"

    result = await with_retry(eventual_success, max_retries=5)
    assert result == "success"
    assert call_count == 3


async def test_with_retry_ultimate_fail():
    """最大リトライ回数で全て失敗すると例外が上がる。"""
    with pytest.raises(ValueError):
        await with_retry(_fail_func, max_retries=2)


async def test_with_retry_default_params():
    """デフォルトパラメータで動作する。"""
    async def always_fail():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await with_retry(always_fail)


async def test_with_retry_backoff_timing(monkeypatch):
    """指数バックオフで遅延が増える。

    ``with_retry`` は FULL JITTER（``delay * (0.5 + random())``）を適用するため、
    Sleep 値はランダム要素を含む。よって正確な値ではなく、
    各試行の基准値 ``initial_delay * backoff_factor ** (attempt-1)`` に対する
    区間 ``[0.5 * base, 1.5 * base]`` に入ることを検証する。
    """
    async def failing_func():
        raise ValueError("fail")

    slept: list[float] = []

    async def fake_sleep(d: float):
        slept.append(d)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    with pytest.raises(ValueError):
        await with_retry(failing_func, max_retries=3, initial_delay=0.5, backoff_factor=2.0)

    assert len(slept) == 2, f"sleep が 2 回のはずが {len(slept)} 回"

    for waited, base in zip(slept, (0.5, 1.0), strict=True):
        assert 0.5 * base <= waited <= 1.5 * base, (
            f"{waited} が FULL JITTER の範囲 [{0.5 * base}, {1.5 * base}] に入らない"
        )

    # FULL JITTER では試行間で単調増加は保証されないため、
    # 「全 sleep が有限かつ上限内」という点上界のみを確認する。
    assert max(slept) <= 1.5 * 1.0


async def test_with_retry_does_not_retry_permanent_4xx(monkeypatch):
    """408 / 409 / 429 を除く 4xx はクライアント起因で恒久的なためリトライしない。"""
    calls = 0

    class BadRequest(Exception):
        status_code = 400

    async def failing_func():
        nonlocal calls
        calls += 1
        raise BadRequest("schema mismatch")

    slept: list[float] = []

    async def fake_sleep(d: float):
        slept.append(d)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    with pytest.raises(BadRequest):
        await with_retry(failing_func, max_retries=5)

    assert calls == 1, "恒久的 4xx は 1 回目で送出し、リトライしない"
    assert slept == []


@pytest.mark.parametrize("status_code", [408, 409, 429])
async def test_with_retry_retries_retryable_4xx(status_code, monkeypatch):
    """408 / 409 / 429 は一時的なのでリトライ対象のまま。"""
    calls = 0

    async def failing_func():
        nonlocal calls
        calls += 1
        err = ValueError("transient")
        err.status_code = status_code
        raise err

    async def fake_sleep(d: float):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    with pytest.raises(ValueError):
        await with_retry(failing_func, max_retries=3)

    assert calls == 3


async def test_with_retry_honours_server_retry_after(monkeypatch):
    """サーバ指定の Retry-After はジッターせずそのまま（上限のみ）尊重する。"""
    calls = 0

    async def failing_func():
        nonlocal calls
        calls += 1
        err = ValueError("429 too many requests")
        err.retry_after = 7.0
        raise err

    slept: list[float] = []

    async def fake_sleep(d: float):
        slept.append(d)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    with pytest.raises(ValueError):
        await with_retry(
            failing_func,
            max_retries=3,
            initial_delay=0.5,
            max_retry_after_seconds=120.0,
        )

    assert calls == 3
    # 3 試行なので sleep は 2 回。両方ともサーバ指定値がそのまま使われる。
    assert slept == [7.0, 7.0]


async def test_with_retry_caps_server_retry_after(monkeypatch):
    """サーバ指定値が巨大でも max_retry_after_seconds で頭打ちになる。"""
    async def failing_func():
        err = ValueError("429")
        err.retry_after = 9999.0
        raise err

    slept: list[float] = []

    async def fake_sleep(d: float):
        slept.append(d)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    with pytest.raises(ValueError):
        await with_retry(failing_func, max_retries=2, max_retry_after_seconds=30.0)

    assert slept == [30.0]
