"""Robust LLM Fallback and Retry Enhancements (Improvement Proposal 3)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


async def robust_execute_with_fallbacks(
    primary_fn: Callable[[], Coroutine[Any, Any, Any]],
    fallback_fns: list[Callable[[], Coroutine[Any, Any, Any]]],
    on_failure: Callable[[Exception, int], None] | None = None,
    *,
    provider_names: list[str] | None = None,
) -> Any:
    """Execute primary LLM call with a sequence of fallback functions and robust exception recovery.

    Args:
        primary_fn: 主系の LLM 呼び出し。
        fallback_fns: フォールバック呼び出しのリスト。
        on_failure: 各試行失敗時のコールバック (exception, attempt_index)。
        provider_names: 各試行のプロバイダ名（構造化ログ用、任意）。

    Raises:
        RuntimeError: 全試行が失敗した場合。元の最後の例外を原因チェーン
            (``raise ... from last_exc``) として保持する。
    """
    all_fns = [primary_fn] + fallback_fns
    last_exc: Exception | None = None

    for idx, fn in enumerate(all_fns):
        provider = provider_names[idx] if provider_names and idx < len(provider_names) else f"provider_{idx}"
        start = time.perf_counter()
        try:
            result = await fn()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.info(
                "LLM execution attempt %d (%s) succeeded in %.1fms",
                idx + 1,
                provider,
                elapsed_ms,
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            last_exc = exc
            logger.warning(
                "LLM execution attempt %d (%s) failed in %.1fms: %s: %r",
                idx + 1,
                provider,
                elapsed_ms,
                type(exc).__name__,
                exc,
            )
            if on_failure is not None:
                try:
                    on_failure(exc, idx)
                except Exception:
                    logger.exception("on_failure callback raised; ignoring")

    if last_exc:
        raise RuntimeError(
            f"All {len(all_fns)} LLM fallback execution paths failed; last error: {type(last_exc).__name__}: {last_exc}"
        ) from last_exc
    raise RuntimeError("All LLM fallback execution paths failed without explicit exception.")
