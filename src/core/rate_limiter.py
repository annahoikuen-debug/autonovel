from __future__ import annotations

import asyncio
import time

from src.core.observability import StructuredLogger

logger = StructuredLogger(__name__)


class TokenBucket:
    """
    Token Bucketアルゴリズムに基づいたレートリミッター。
    APIリクエストの流量を制御し、429 Too Many Requestsを未然に防ぐ。
    """

    def __init__(self, capacity: float, fill_rate: float, name: str = "default"):
        """
        Args:
            capacity: バケットの最大容量（最大バースト量）
            fill_rate: 1秒あたりのトークン補充量
            name: リミッターの識別名（ログ用）
        """
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.name = name
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def consume(self, tokens: float = 1.0) -> bool:
        """
        トークンを消費しようと試みる。

        Args:
            tokens: 消費するトークン数（通常は1リクエスト=1トークン）

        Returns:
            True: 消費に成功し、リクエストを即座に実行可能
            False: トークン不足によりリクエスト不可

        Raises:
            ValueError: tokens がバケット容量を超えている場合 (永久待機になるため)
        """
        self._validate_request(tokens)
        async with self._get_lock():
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def _validate_request(self, tokens: float) -> None:
        """要求量がバケット容量を超えているかを検証する。

        ``_refill`` は capacity で頭打ちになるため、capacity を超える要求は
        ``self.tokens >= tokens`` が永久に成立せず、待機ループが終了しない。
        """
        if tokens <= 0:
            raise ValueError(f"RateLimiter [{self.name}]: tokens must be positive, got {tokens}")
        if tokens > self.capacity:
            raise ValueError(
                f"RateLimiter [{self.name}]: requested {tokens} tokens exceeds "
                f"capacity {self.capacity}; the request could never be served"
            )

    def _refill(self):
        """現在の時刻に基づいてトークンを補充する。"""
        now = time.monotonic()
        delta = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + delta * self.fill_rate)
        self.last_update = now

    async def wait_and_consume(self, tokens: float = 1.0):
        """
        トークンが補充されるまで待機し、消費する。

        Args:
            tokens: 消費するトークン数

        Raises:
            ValueError: tokens がバケット容量を超えている場合。
                補充は capacity で頭打ちになるため永久に待っても満たず、
                リクエストを掴んだまま終了しない。
        """
        self._validate_request(tokens)
        while True:
            async with self._get_lock():
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # 次にトークンが補充されるまでの待機時間を計算
                wait_time = (tokens - self.tokens) / self.fill_rate

            logger.debug(f"RateLimiter [{self.name}]: Token shortage. Waiting {wait_time:.2f}s...")
            # ジッターを追加して、同時に待機していた大量のリクエストが一度に集中する「サンダリングヘルド」を防ぐ
            import random

            jitter = random.uniform(0, 0.1)
            await asyncio.sleep(wait_time + jitter)

    async def adjust_rate(self, factor: float):
        """
        補充レートを動的に調整する（AdaptiveCooldownからのフィードバック用）。

        in-flight（待機中・消費済み）の予算を壊さないよう、
        現在のトークン残量は capacity 以下に収め直す。

        Args:
            factor: 乗数 (例: 0.5 でレート半分に低下, 1.1 で10%回復)

        Raises:
            ValueError: factor が正でない場合
        """
        if factor <= 0:
            raise ValueError(f"RateLimiter [{self.name}]: factor must be positive, got {factor}")
        async with self._get_lock():
            old_rate = self.fill_rate
            self.fill_rate = max(0.01, self.fill_rate * factor)
            # 容量と残量の整合を保つ (残量が capacity 超なら頭打ちに戻す)
            if self.tokens > self.capacity:
                self.tokens = self.capacity
            logger.info(
                f"RateLimiter [{self.name}]: Adjusted fill_rate {old_rate:.2f} -> {self.fill_rate:.2f} (factor={factor})"
            )

    def get_status(self) -> dict:
        """現在のバケット状態を返す。"""
        return {
            "name": self.name,
            "tokens": self.tokens,
            "capacity": self.capacity,
            "fill_rate": self.fill_rate,
        }
