from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from prometheus_client import Counter

from .circuit_breaker import LLMCircuitBreaker
from .fallback_policy import ALLOW_MOCK_ENV, FallbackPolicy, _mock_allowed
from src.services.llm.provider_failover import ProviderFailoverManager

logger = logging.getLogger(__name__)


llm_failover_total = Counter(
    "llm_failover_total",
    "Number of LLM provider failovers",
    ("from_provider", "to_provider", "reason"),
)
failover_counter = llm_failover_total


def normalize_schema_prompt(prompt: str, response_schema: Any | None) -> str:
    if response_schema is None:
        return prompt
    if hasattr(response_schema, "model_json_schema"):
        schema: Any = response_schema.model_json_schema()
    elif hasattr(response_schema, "schema"):
        schema = response_schema.schema()
    elif isinstance(response_schema, type):
        try:
            schema = response_schema.model_json_schema()
        except AttributeError:
            schema = {"type": "object", "title": getattr(response_schema, "__name__", "Response")}
    else:
        schema = response_schema
    try:
        schema_text = json.dumps(schema, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        schema_text = str(schema)
    return (
        f"{prompt}\n\n"
        "出力は次のJSONスキーマに厳密に従った有効なJSONのみとしてください。\n"
        f"```json\n{schema_text}\n```"
    )


class ResilientLLMGateway:
    # プロセス共有の ProviderFailoverManager。ResilientLLMGateway は
    # src/backend/engine.py と src/backend/routers/system.py の 2 箇所で
    # 生成されるため、インスタンスごとに作るとブレーカー状態が共有されず
    # どちらかの网关だけ衰退する。
    _failover_manager_singleton: ProviderFailoverManager | None = None

    def __init__(
        self,
        circuit_breaker: LLMCircuitBreaker | None = None,
        providers: Mapping[str, Any] | None = None,
        default_provider: str = "openai",
        fallback_policy: FallbackPolicy | Mapping[str, list[str]] | None = None,
        provider_factory: Any | None = None,
        *,
        backoff_base_seconds: float = 0.1,
        max_backoff_seconds: float = 2.0,
        max_retry_after_seconds: float = 120.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        call_timeout_seconds: float | None = None,
    ) -> None:
        self.circuit_breaker = circuit_breaker or LLMCircuitBreaker()
        self.providers = dict(providers or {})
        self.default_provider = default_provider
        if isinstance(fallback_policy, FallbackPolicy):
            self.fallback_policy = fallback_policy
        else:
            self.fallback_policy = FallbackPolicy(fallback_policy)
        self.provider_factory = provider_factory
        self.backoff_base_seconds = max(0.0, backoff_base_seconds)
        self.max_backoff_seconds = max(0.0, max_backoff_seconds)
        # サーバーが明示した Retry-After の上限。max_backoff_seconds は
        # 「自前で計算した」指数バックオフ専用であり、レート制限ウィンドウを
        # 切る長さの待機を禁止するために用到してはならない。
        self.max_retry_after_seconds = max(0.0, max_retry_after_seconds)
        self._sleep = sleep or asyncio.sleep
        # プロバイダ呼び出し全体の期限。None なら環境変数
        # AUTONOVEL_LLM_CALL_TIMEOUT_SECONDS、既定 300 秒。
        # 以前は timeout が一切無く、応答無いプロバイダでパイプラインが
        # 無期限にハングしていた。
        if call_timeout_seconds is not None:
            self.call_timeout_seconds = float(call_timeout_seconds)
        else:
            raw = os.environ.get("AUTONOVEL_LLM_CALL_TIMEOUT_SECONDS", "").strip()
            try:
                self.call_timeout_seconds = float(raw) if raw else 300.0
            except ValueError:
                logger.warning(
                    "AUTONOVEL_LLM_CALL_TIMEOUT_SECONDS=%r is not a number; using 300.0",
                    raw,
                )
                self.call_timeout_seconds = 300.0
        if self.call_timeout_seconds <= 0:
            self.call_timeout_seconds = 300.0
        # プロセス共有の ProviderFailoverManager（インスタンス毎の生成をやめる）
        if ResilientLLMGateway._failover_manager_singleton is None:
            ResilientLLMGateway._failover_manager_singleton = ProviderFailoverManager()
        self._failover_manager = ResilientLLMGateway._failover_manager_singleton

    def _failover_breaker_for(self, provider: str) -> Any | None:
        """プロバイダ名に対応する_failover_manager_のブレーカーを返す。

        以前は ``breakers.get(provider, breakers["gemini"])`` としており、
        (1) dict.get の default 引数は常に評価されるため "gemini" が無くても
        KeyError になり、(2) ollama/vllm/mock が Gemini の健全性で
        遮断されていた。未知のプロバイダは「遮断しない」として扱う。
        """
        return self._failover_manager.breakers.get(provider)

    async def generate_text(
        self,
        prompt: str,
        primary_provider: str | None = None,
        system_instruction: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Any:
        response_schema = kwargs.pop("response_schema", None)
        normalized_prompt = normalize_schema_prompt(prompt, response_schema)
        if response_schema is not None:
            kwargs.setdefault("response_schema", response_schema)
        return await self._generate(
            prompt=normalized_prompt,
            primary_provider=primary_provider,
            system_instruction=system_instruction,
            temperature=temperature,
            method_name="generate_text",
            kwargs=kwargs,
        )

    async def generate_json(
        self,
        prompt: str,
        response_schema: Any | None = None,
        primary_provider: str | None = None,
        system_instruction: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Any:
        normalized_prompt = normalize_schema_prompt(prompt, response_schema)
        return await self._generate(
            prompt=normalized_prompt,
            primary_provider=primary_provider,
            system_instruction=system_instruction,
            temperature=temperature,
            method_name="generate_json",
            kwargs={**kwargs, "response_schema": response_schema},
        )

    async def _generate(
        self,
        prompt: str,
        primary_provider: str | None,
        system_instruction: str | None,
        temperature: float,
        method_name: str,
        kwargs: dict[str, Any],
    ) -> Any:
        primary = self._canonical_provider(primary_provider or self.default_provider)
        candidates = [primary, *self.fallback_policy.get_fallback_sequence(primary)]
        seen: set[str] = set()
        last_error: Exception | None = None
        last_unavailable: Exception | None = None

        for attempt, provider in enumerate(candidates):
            if provider in seen:
                continue
            seen.add(provider)
            next_provider = self._next_candidate(candidates, attempt, seen)
            if provider == "mock" and not _mock_allowed():
                # 実プロバイダが全部失敗したときに、MockAdapter の出力が
                # 本物の LLM 出力と区別できないままパイプラインを流していた。
                last_unavailable = RuntimeError(
                    "Refusing to use the 'mock' LLM provider in production. "
                    f"Set {ALLOW_MOCK_ENV}=1 only for tests/CI."
                )
                logger.error("%s", last_unavailable)
                if next_provider:
                    self._record_failover(provider, next_provider, "mock_blocked")
                continue
            if not self.circuit_breaker.can_execute(provider):
                last_unavailable = RuntimeError(f"Circuit breaker is OPEN for {provider}")
                if next_provider:
                    self._record_failover(provider, next_provider, "circuit_open")
                continue
            # Additional check using ProviderFailoverManager（プロバイダが登録されている場合のみ）
            failover_breaker = self._failover_breaker_for(provider)
            if failover_breaker is not None and not failover_breaker.can_execute():
                last_unavailable = RuntimeError(f"Failover manager circuit breaker is OPEN for {provider}")
                if next_provider:
                    self._record_failover(provider, next_provider, "circuit_open")
                continue

            llm_provider = self._get_provider(provider)
            if llm_provider is None:
                last_unavailable = RuntimeError(f"LLM provider is unavailable: {provider}")
                if next_provider:
                    self._record_failover(provider, next_provider, "unavailable")
                continue

            try:
                result = await self._invoke(
                    llm_provider,
                    provider,
                    method_name,
                    prompt,
                    system_instruction,
                    temperature,
                    kwargs,
                )
                self.circuit_breaker.record_success(provider)
                return result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                self.circuit_breaker.record_failure(provider, exc)
                reason = "rate_limit" if self._is_rate_limit_error(exc) else "error"
                if next_provider:
                    self._record_failover(provider, next_provider, reason)
                if reason == "rate_limit":
                    await self._backoff(exc, attempt)

        if last_error is not None:
            raise RuntimeError(f"All LLM providers failed: {last_error}") from last_error
        if last_unavailable is not None:
            raise last_unavailable
        raise RuntimeError(f"No LLM provider is available for {primary}")

    async def _invoke(
        self,
        provider: Any,
        provider_name: str,
        method_name: str,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        kwargs: dict[str, Any],
    ) -> Any:
        method = getattr(provider, method_name, None)
        if method is None and callable(provider):
            method = provider
        if method is None:
            raise AttributeError(f"Provider {provider_name} has no {method_name} method")

        call_kwargs = dict(kwargs)
        system_prompt = call_kwargs.pop("system_prompt", None)
        effective_system = system_instruction if system_instruction is not None else system_prompt
        temperature_value = call_kwargs.pop("temp", temperature)
        response_schema = call_kwargs.pop("response_schema", None)
        response_format = call_kwargs.pop("response_format", None)
        if response_schema is not None:
            call_kwargs["response_schema"] = response_schema
        if response_format is not None:
            call_kwargs["response_format"] = response_format

        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):
            signature = None
        if signature is not None:
            parameters = signature.parameters
            accepts_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if not accepts_kwargs:
                call_kwargs = {
                    key: value
                    for key, value in call_kwargs.items()
                    if key in parameters
                }
            call_args: dict[str, Any] = {}
            if "model_name" in parameters:
                call_args["model_name"] = provider_name
            if "prompt" in parameters:
                call_args["prompt"] = prompt
            if "system_instruction" in parameters:
                call_args["system_instruction"] = effective_system
            if "system_prompt" in parameters:
                call_args["system_prompt"] = effective_system
            if "temperature" in parameters:
                call_args["temperature"] = temperature_value
            if "temp" in parameters:
                call_args["temp"] = temperature_value
            if "response_schema" in parameters and response_schema is not None:
                call_args["response_schema"] = response_schema
            if "response_format" in parameters:
                if response_format is not None:
                    call_args["response_format"] = response_format
                elif response_schema is not None:
                    call_args["response_format"] = {"type": "json_object"}
            current_time = time.time()
            if "context" in parameters and "context" not in call_kwargs:
                call_args["context"] = current_time
            call_kwargs = {**call_args, **call_kwargs}
            try:
                result = method(**call_kwargs)
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                result = method(prompt, provider_name, effective_system, temperature_value, **call_kwargs)
        else:
            result = method(prompt, provider_name, effective_system, temperature_value, **call_kwargs)
        if inspect.isawaitable(result):
            # 応答のないプロバイダでパイプラインが無期限ハングするのを防ぐ。
            # クライアント層（gemini 120s/180s, openai 120s）よりも外側の
            # ガードとして機能する。TimeoutError は failover 対象の
            # 一時エラーとして扱われ、次のプロバイダへ退避する。
            async with asyncio.timeout(self.call_timeout_seconds):
                return await result
        return result

    def _get_provider(self, provider_name: str) -> Any | None:
        provider = self.providers.get(provider_name)
        if provider is not None:
            return provider
        if self.provider_factory is None:
            return None
        for method_name in ("get_provider", "get_client", "create"):
            method = getattr(self.provider_factory, method_name, None)
            if callable(method):
                try:
                    provider = method(provider_name)
                except TypeError:
                    provider = method()
                if provider is not None:
                    self.providers[provider_name] = provider
                    return provider
        if callable(self.provider_factory):
            try:
                provider = self.provider_factory(provider_name)
            except TypeError:
                provider = self.provider_factory()
            if provider is not None:
                self.providers[provider_name] = provider
                return provider
        return None

    def _canonical_provider(self, provider_name: str) -> str:
        provider = provider_name.strip().lower()
        if provider in self.providers or provider in {
            "claude",
            "openai",
            "gemini",
            "ollama",
            "vllm",
            "mock",
        }:
            return provider
        lowered = provider.replace("_", "-")
        if "claude" in lowered or "anthropic" in lowered:
            return "claude"
        if "gemini" in lowered or "google" in lowered:
            return "gemini"
        if "ollama" in lowered:
            return "ollama"
        if "vllm" in lowered:
            return "vllm"
        if "mock" in lowered:
            return "mock"
        if "openai" in lowered or "gpt" in lowered or "openrouter" in lowered:
            return "openai"
        return provider

    @staticmethod
    def _next_candidate(
        candidates: list[str], attempt: int, seen: set[str]
    ) -> str | None:
        for candidate in candidates[attempt + 1 :]:
            if candidate not in seen:
                return candidate
        return None

    @staticmethod
    def _record_failover(from_provider: str, to_provider: str, reason: str) -> None:
        llm_failover_total.labels(from_provider, to_provider, reason).inc()

    async def _backoff(self, error: Exception, attempt: int) -> None:
        retry_after = getattr(error, "retry_after", None)
        if retry_after is None:
            response = getattr(error, "response", None)
            if response is not None:
                retry_after = getattr(response, "retry_after", None)
        if retry_after is None:
            message = str(error)
            match = re.search(r"retry[- ]?after[:=]\s*(\d+(?:\.\d+)?)", message, re.I)
            retry_after = float(match.group(1)) if match else None
        if retry_after is None:
            # 導出バックオフのみ max_backoff_seconds で制限する
            retry_after = min(
                self.backoff_base_seconds * (2 ** max(attempt, 0)),
                self.max_backoff_seconds,
            )
            ceiling = self.max_backoff_seconds
        else:
            # サーバー指定の Retry-After は、レート制限ウィンドウが解けるまで
            # 待つ必要があるため、桁違いの上限を適用する
            ceiling = self.max_retry_after_seconds
        if retry_after > 0:
            await self._sleep(min(float(retry_after), ceiling))

    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        if error.__class__.__name__.lower() in {
            "ratelimiterror",
            "ratelimitexception",
            "resourceexhausted",
        }:
            return True
        status_code = getattr(error, "status_code", None)
        if status_code is None:
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", None)
        if status_code == 429:
            return True
        message = str(error).lower()
        return "429" in message or "rate limit" in message or "too many requests" in message

    def status(self) -> dict[str, Any]:
        return self.circuit_breaker.snapshot()

    def reset(self, provider_name: str | None = None) -> None:
        self.circuit_breaker.reset(provider_name)
