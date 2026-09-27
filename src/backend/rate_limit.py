"""IP ベースレートリミッター (Redis分散対応 + プロセス内フォールバック).

`check()` は `async` であり、Redis アクセスも非同期クライアントで行う。
これにより `async def` のハンドラから呼んでもイベントループをブロックしない。
"""

from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

from src.backend.redis_util import get_async_redis_client

logger = logging.getLogger(__name__)


def _parse_trusted_proxies(raw: str | None) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """`TRUSTED_PROXY_CIDRS` をネットワーク集合に変換する（不正値は除外）。"""
    if not raw:
        return ()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXY_CIDRS の不正なエントリを無視します: %s", entry)
    return tuple(networks)


class RateLimiter:
    """スライディングウィンドウ方式のレートリミッター (Redis対応・メモリフォールバック)."""

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60,
        prefix: str = "rate_limit",
        trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] | None = None,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._prefix = prefix
        self._lock = threading.Lock()
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._trusted_proxies = trusted_proxies

    def _is_trusted_proxy(self, host: str) -> bool:
        proxies = self._trusted_proxies
        if proxies is None:
            # 遅延解決，避免在 import 時に settings を読む
            from src.backend.config import settings

            proxies = _parse_trusted_proxies(getattr(settings, "TRUSTED_PROXY_CIDRS", ""))
            self._trusted_proxies = proxies
        if not proxies:
            return False
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(addr in net for net in proxies)

    def _get_client_ip(self, request: Request) -> str:
        """実クライアント IP を取得する。

        `X-Forwarded-For` は信頼したプロキシからのみ採用する。
        従来の実装は検証なしで常に先頭要素を採用していたため、
        ヘッダーを偽装すればレート制限を完全に回避できた。
        """
        peer = request.client.host if request.client else None
        forwarded = request.headers.get("X-Forwarded-For")

        if forwarded and peer and self._is_trusted_proxy(peer):
            for candidate in (c.strip() for c in forwarded.split(",")):
                if not candidate:
                    continue
                # XFF は "client, proxy1, proxy2" の順。trusted proxy 群の
                # 右端から走査し、最初の非 trusted エントリを実クライアントとする。
                try:
                    addr = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if not any(
                    addr in net for net in (self._trusted_proxies or ())
                ):
                    return candidate
            return forwarded.split(",")[0].strip()

        if peer:
            return peer
        return "unknown"

    async def check(self, request: Request) -> None:
        client_ip = self._get_client_ip(request)

        # 1. Redis が利用可能な場合は Redis カウンタで分散チェック（非同期）
        redis_client = await get_async_redis_client()
        if redis_client is not None:
            try:
                key = f"{self._prefix}:{client_ip}"
                current_count = await redis_client.incr(key)
                if current_count == 1:
                    await redis_client.expire(key, self._window)
                if current_count > self._max:
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded. Try again later.",
                    )
                return
            except HTTPException:
                raise
            except Exception as e:
                logger.debug("Redis rate limiter check failed, falling back to memory: %s", e)

        # 2. メモリ内フォールバック
        now = time.time()
        with self._lock:
            timestamps = self._requests[client_ip]
            self._requests[client_ip] = [t for t in timestamps if now - t < self._window]
            if len(self._requests[client_ip]) >= self._max:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Try again later.",
                )
            self._requests[client_ip].append(now)

    def reset(self) -> None:
        """テスト用のリセットメソッド."""
        with self._lock:
            self._requests.clear()


generate_limiter = RateLimiter(max_requests=10, window_seconds=60, prefix="rate_limit:gen")
stream_limiter = RateLimiter(max_requests=3, window_seconds=60, prefix="rate_limit:stream")

__all__ = ["RateLimiter", "generate_limiter", "stream_limiter"]
