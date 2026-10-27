"""CancellationToken の回帰テスト（PLAN_W6 Step 2）。"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.core.cancellation import CancellationToken  # noqa: E402


@pytest.mark.asyncio
async def test_starts_uncancelled():
    assert CancellationToken("t").is_cancelled() is False


@pytest.mark.asyncio
async def test_cancel_flips_flag():
    tok = CancellationToken("t")
    tok.cancel()
    assert tok.is_cancelled() is True


@pytest.mark.asyncio
async def test_wait_returns_after_cancel():
    tok = CancellationToken("t")
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, tok.cancel)
    await asyncio.wait_for(tok.wait(), timeout=1.0)
    assert tok.is_cancelled()


@pytest.mark.asyncio
async def test_raise_if_cancelled_raises_cancelled_error():
    tok = CancellationToken("t")
    tok.cancel()
    with pytest.raises(asyncio.CancelledError):
        tok.raise_if_cancelled()


@pytest.mark.asyncio
async def test_raise_if_cancelled_is_noop_when_active():
    CancellationToken("t").raise_if_cancelled()  # 例外_none


@pytest.mark.asyncio
async def test_usable_as_event():
    tok = CancellationToken("t")
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, tok.cancel)
    await asyncio.wait_for(tok.cancelled_event.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_cancel_from_another_thread_does_not_raise():
    tok = CancellationToken("t")
    t = threading.Thread(target=tok.cancel)
    t.start()
    t.join()
    assert tok.is_cancelled() is True


@pytest.mark.asyncio
async def test_name_is_preserved():
    assert CancellationToken("prefetch").name == "prefetch"
    assert CancellationToken().name == ""
