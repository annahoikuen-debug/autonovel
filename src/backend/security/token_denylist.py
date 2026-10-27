"""JWT 失効リスト (denylist)。

JWT はステートレスなので、発行してしまったトークンは `exp` まで有効なまま
残る。「ログアウトしたのにトークンがまだ使える」を防ぐには、失効済みの
トークン単体を拒否する仕組みが要る。本モジュールは ``jti`` (トークン単体の
識別子) をキーに、失効したトークンを記録する。

格納は Redis を優先し、接続できない環境ではプロセス内メモリにフォールバック
する（``rate_limit.py`` と同一の方針）。

fail-open について
------------------
Redis が落ちた場合、失効情報が分散プロセス間に届かない。可用性を優先して
フェイルオープン (拒否しない) とする。フェイルクローズにすると Redis の
一時的な障害で全リクエストが 401 になり、認証基盤全体が止まるため。
"""

from __future__ import annotations

import logging
import threading
import time

from src.backend.redis_util import get_async_redis_client

logger = logging.getLogger(__name__)

#: Redis キーのプレフィックス。
KEY_PREFIX = "auth:denylist:"

#: ``exp`` が無いトークンを失効させる際の既定 TTL (秒)。
DEFAULT_TTL_SECONDS = 24 * 60 * 60

#: メモリフォールバックで保持するキー数の上限。
#:
#: 攻撃者が大量の異なるトークンを受け取り続けて失効させると、メモリが
#: 無制限に増えてしまう。``RateLimiter.MAX_TRACKED_KEYS`` と同じ理由で上限を設ける。
MAX_MEMORY_ENTRIES = 10_000

#: jti -> 失効する時刻 (epoch 秒)。時刻が来たら自然に消える。
_memory: dict[str, float] = {}
_lock = threading.Lock()


def _ttl_seconds(exp: float | None, now: float) -> int:
    """トークンの残存寿命ぶんの TTL を返す。

    失効記録はトークンが生きている間だけ必要。トークンが消えた後に
    記録が残り続けるのは無駄なので、``exp`` をそのまま TTL にする。
    """
    if exp is None:
        return DEFAULT_TTL_SECONDS
    return max(1, int(exp - now))


def _purge_expired(now: float) -> None:
    """有効期限が切れた失効記録を掃き出す。

    呼び出しは ``_lock`` を保持した状態で行うこと。
    """
    expired = [jti for jti, exp in _memory.items() if exp <= now]
    for jti in expired:
        del _memory[jti]


def _enforce_capacity(now: float) -> None:
    """上限を超えていたら、最も早く失効する（= 最も損失が小さい）記録から捨てる。

    呼び出しは ``_lock`` を保持した状態で行うこと。
    """
    overflow = len(_memory) - MAX_MEMORY_ENTRIES
    if overflow <= 0:
        return
    # exp が小さい = すでに近い将来消える記録から捨てる。
    victims = sorted(_memory.items(), key=lambda kv: kv[1])[:overflow]
    for jti, _ in victims:
        del _memory[jti]
    logger.warning(
        "Token denylist capacity reached (%d): dropped %d entries nearest expiry",
        MAX_MEMORY_ENTRIES,
        overflow,
    )


async def revoke(jti: str | None, exp: float | None = None) -> None:
    """``jti`` を失効させる。

    Args:
        jti: 失効対象のトークン ID。空なら何もしない。
        exp: トークンの ``exp`` クレーム (epoch 秒)。与えれば TTL に使う。
    """
    if not jti:
        return

    now = time.time()
    ttl = _ttl_seconds(exp, now)

    client = await get_async_redis_client()
    if client is not None:
        try:
            await client.set(KEY_PREFIX + jti, "1", ex=ttl)
            return
        except Exception as e:
            logger.warning("Redis denylist write failed, falling back to memory: %s", e)

    with _lock:
        _purge_expired(now)
        _enforce_capacity(now)
        _memory[jti] = now + ttl


async def is_revoked(jti: str | None) -> bool:
    """``jti`` が失効済みなら ``True``。

    ``jti`` が無いトークン（本機能より前に発行された分）は失効できないため
    ``False`` を返す。そのトークンは ``exp`` まで自然に有効。
    """
    if not jti:
        return False

    client = await get_async_redis_client()
    if client is not None:
        try:
            return bool(await client.exists(KEY_PREFIX + jti))
        except Exception as e:
            logger.warning("Redis denylist read failed, falling back to memory: %s", e)

    with _lock:
        exp = _memory.get(jti)
        if exp is None:
            return False
        if exp <= time.time():
            del _memory[jti]
            return False
        return True


def reset() -> None:
    """メモリフォールバックの内容を空にする（テスト用）。"""
    with _lock:
        _memory.clear()


__all__ = ["KEY_PREFIX", "revoke", "is_revoked", "reset"]
