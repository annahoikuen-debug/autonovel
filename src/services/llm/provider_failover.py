"""プロバイダーフェイルオーバーマネージャー。"""
from __future__ import annotations
from typing import Any, Callable, Coroutine
from src.services.llm.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException


class ProviderFailoverManager:
    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {
            "gemini": CircuitBreaker(failure_threshold=3, recovery_timeout=30.0),
            "openai": CircuitBreaker(failure_threshold=3, recovery_timeout=30.0),
            "claude": CircuitBreaker(failure_threshold=3, recovery_timeout=30.0),
        }

    async def execute_with_fallback(
        self,
        primary_provider: str,
        fallback_provider: str,
        primary_fn: Callable[[], Coroutine[Any, Any, Any]],
        fallback_fn: Callable[[], Coroutine[Any, Any, Any]],
    ) -> tuple[Any, str]:
        """Primaryで試行し、遮断または失敗時にFallbackを実行する。"""
        # 未知プロバイダが他プロバイダのブレーカー状態を継承しないよう、
        # 未登録なら None（= 遮断なし）として扱う。
        p_breaker = self.breakers.get(primary_provider)
        f_breaker = self.breakers.get(fallback_provider)

        if p_breaker is None or p_breaker.can_execute():
            try:
                res = await primary_fn()
                if p_breaker is not None:
                    p_breaker.record_success()
                return res, primary_provider
            except Exception:
                if p_breaker is not None:
                    p_breaker.record_failure()

        # Fallback 実行
        if f_breaker is not None and not f_breaker.can_execute():
            raise CircuitBreakerOpenException("すべての利用可能なプロバイダーが遮断されています")

        try:
            res = await fallback_fn()
            if f_breaker is not None:
                f_breaker.record_success()
            return res, fallback_provider
        except Exception as e:
            if f_breaker is not None:
                f_breaker.record_failure()
            raise e
