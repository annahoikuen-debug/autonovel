"""`src/backend/rate_limit.py` のメモリフォールバックのキー管理テスト。

このテストが固定する問題
----------------------
`RateLimiter` のメモリ内フォールバックは `defaultdict(list)` で IP キーを保持するが、
キー自体は自動削除されない。大量の異なる IP（攻撃者がスプーフした
`X-Forwarded-For`、分散スキャン、ボットネット）から 1 リクエストずつ来ると、
**キー数だけが無制限に増える**（メモリ枯渇の DoS）。

そのため、一定間隔で「ウィンドウ外のキーを掃き出す」清掃と、
追跡キー数の上限による切り詰めを実装済み。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.backend.rate_limit import RateLimiter


def _request(ip: str) -> MagicMock:
    """`_get_client_ip` が peer (`request.client.host`) を採用する構成の要求。

    X-Forwarded-For 経路は ``TRUSTED_PROXY_CIDRS`` の設定が必要で、
    未設定だと必ず ``"unknown"`` に落ちるため使わない。
    """
    req = MagicMock()
    req.headers = {}
    req.client = MagicMock()
    req.client.host = ip
    return req


def _check(limiter: RateLimiter, ip: str) -> None:
    asyncio.run(limiter.check(_request(ip)))


def test_idle_keys_are_evicted_after_window():
    """ウィンドウ期間中有に一度しか来ていない IP は清掃で消える（無制限増加の防止）。"""
    limiter = RateLimiter(max_requests=100, window_seconds=1)
    # 清掃を毎回走らせる（テストでは既定の 60 秒を待たないため 0 にする）
    limiter.EVICTION_INTERVAL_SECONDS = 0

    for i in range(5):
        _check(limiter, f"10.0.0.{i}")
    assert len(limiter._requests) == 5

    time.sleep(1.05)  # ウィンドウ (1 秒) より長く待つ
    _check(limiter, "10.0.0.99")

    assert "10.0.0.0" not in limiter._requests, "期限切れのキーが残ったまま増加している"
    assert "10.0.0.99" in limiter._requests


def test_tracked_key_count_is_capped():
    """追跡キー数の上限を超えたら古いキーから切り詰められる。"""
    limiter = RateLimiter(max_requests=10_000, window_seconds=3600)
    limiter.EVICTION_INTERVAL_SECONDS = 0
    limiter.MAX_TRACKED_KEYS = 10

    for i in range(25):
        _check(limiter, f"10.1.0.{i}")

    assert len(limiter._requests) <= 10, (
        f"上限を超えてキーを保持している: {len(limiter._requests)}"
    )


def test_active_window_still_rate_limits_after_eviction_change():
    """清掃を入れても通常のスライディングウィンドウ制限は変わらない。"""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    limiter.EVICTION_INTERVAL_SECONDS = 0

    _check(limiter, "192.168.0.1")
    _check(limiter, "192.168.0.1")
    _check(limiter, "192.168.0.1")

    with pytest.raises(HTTPException) as exc:
        _check(limiter, "192.168.0.1")
    assert exc.value.status_code == 429


def test_eviction_is_skipped_within_interval():
    """清掃は毎リクエストではなく間引かれる（CPU を無駄にしない）。"""
    limiter = RateLimiter(max_requests=100, window_seconds=1)
    # 既定の 60 秒間隔は、この 1 秒テストでは一度も走らない
    _check(limiter, "10.2.0.1")
    time.sleep(1.05)
    _check(limiter, "10.2.0.2")

    assert "10.2.0.1" in limiter._requests, (
        "清掃の間隔が尊重されていない（毎リクエストで清掃している）"
    )
