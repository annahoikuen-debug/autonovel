"""LLM API 呼び出し用の指数バックオフリトライヘルパー。"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# 恒久的なクライアントエラーとして明示的に送出すべき例外
# （SDKをimportせずクラス名で判定する）
_NON_RETRYABLE_ERROR_NAMES = frozenset({
    "BadRequestError",
    "UnprocessableEntityError",
    "AuthenticationError",
    "PermissionDeniedError",
    "PermissionDenied",
    "NotFoundError",
    "ConflictError",
    "UnprocessableEntity",
})

# リトライ対象とする一時的なエラー
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})

_RETRYABLE_ERROR_NAMES = frozenset({
    "APIConnectionError",
    "APITimeoutError",
    "APIConnectionTimeoutError",
    "ConnectionError",
    "ConnectTimeout",
    "ConnectError",
    "ReadTimeout",
    "ReadError",
    "RemoteProtocolError",
    "TimeoutException",
    "TimeoutError",
    "TooManyRequests",
    "RateLimitError",
    "RateLimitException",
    "InternalServerError",
    "ServiceUnavailableError",
    "OverloadedError",
    "ResourceExhausted",
})

_RETRY_AFTER_PATTERN = re.compile(r"retry[- ]?after[:=]\s*(\d+(?:\.\d+)?)", re.I)


def _extract_status_code(exc: BaseException) -> int | None:
    """例外から HTTP ステータスコードをダックタイピングで取り出す。

    各プロバイダSDKをimportせずに済むよう、``status_code`` /
    ``response.status_code`` / ``http_status`` を順に参照する。
    """
    for attr in ("status_code", "http_status", "http_status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def is_retryable_exception(exc: BaseException) -> bool:
    """リトライすべき一時的な例外かどうかを判定する。

    判定できない例外（素の例外など）は後方互換のためリトライ対象とする。
    """
    # 恒久的な失敗であることが明示的に示されているもの
    if type(exc).__name__ in _NON_RETRYABLE_ERROR_NAMES:
        return False

    status_code = _extract_status_code(exc)
    if status_code is not None:
        if status_code in _RETRYABLE_STATUS_CODES or status_code >= 500:
            return True
        # 408 / 409 / 429 を除く 4xx はクライアント起因で恒久的
        return False

    # タイムアウト・接続エラーは名前で明示する
    for klass in type(exc).__mro__:
        if klass.__name__ in _RETRYABLE_ERROR_NAMES:
            return True

    # 判定不能な例外は従来どおりリトライ対象（後方互換）
    return True


def _retry_after_seconds(exc: BaseException) -> float | None:
    """例外からサーバ指定の Retry-After を取り出す。"""
    for holder in (exc, getattr(exc, "response", None)):
        if holder is None:
            continue
        value = getattr(holder, "retry_after", None)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    match = _RETRY_AFTER_PATTERN.search(str(exc))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


async def with_retry[T](
    async_func: Callable[[], Coroutine[Any, Any, T]],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_retry_after_seconds: float = 120.0,
) -> T:
    """非同期関数を指数バックオフでリトライ実行する。

    一時的なエラー（429 / 5xx / タイムアウト / 接続エラー）のみリトライし、
    恒久的なクライアントエラー（400 / 401 / 404 等.Schema不整合や
    コンテキスト長超過）は即座に送出す��。
    待機時間にはジッターを加え、サーバ指定の ``Retry-After`` があれば尊重する。
    リトライを使い切った場合は必ず例外を送出する（空値は返さない）。
    """
    delay = initial_delay
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await async_func()
        except Exception as exc:
            last_exception = exc

            if not is_retryable_exception(exc):
                logger.error(
                    "Non-retryable LLM error (attempt %d/%d): %s: %s. Not retrying.",
                    attempt,
                    max_retries,
                    type(exc).__name__,
                    exc,
                )
                raise

            if attempt == max_retries:
                logger.error("All %d retries failed. Last error: %s", max_retries, exc)
                break

            wait = _retry_after_seconds(exc)
            if wait is None:
                # 指数バックオフにジッターを加える（同時リトライの衝突を分散）
                wait = delay * (0.5 + random.random())
            else:
                # サーバ指定値は上限のみ適用する
                wait = min(wait, max(0.0, max_retry_after_seconds))
                logger.info("Honouring server Retry-After of %.1fs", wait)

            logger.warning(
                "LLM call failed (attempt %d/%d): %s: %s. Retrying in %.1fs...",
                attempt,
                max_retries,
                type(exc).__name__,
                exc,
                wait,
            )
            await asyncio.sleep(wait)
            delay *= backoff_factor

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop exited unexpectedly without result or exception.")


__all__ = ["with_retry", "is_retryable_exception"]
