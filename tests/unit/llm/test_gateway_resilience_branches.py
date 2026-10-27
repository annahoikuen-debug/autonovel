"""ResilientLLMGateway の未カバー分岐を網羅する追加テスト。"""
from __future__ import annotations

import asyncio
import inspect

import pytest
from unittest.mock import AsyncMock

from src.llm import resilient_gateway as rg
from src.llm.circuit_breaker import LLMCircuitBreaker
from src.llm.fallback_policy import FallbackPolicy
from src.llm.resilient_gateway import ResilientLLMGateway, normalize_schema_prompt


class _Schema:
    @classmethod
    def model_json_schema(cls):
        return {"type": "object"}


class _OldSchema:
    @classmethod
    def schema(cls):
        return {"type": "object", "legacy": True}


class _NoJsonSchema:
    __name__ = "Weird"


class TestNormalizeSchemaPrompt:
    def test_none_schema_returns_prompt(self):
        assert normalize_schema_prompt("p", None) == "p"

    def test_pydantic_like_instance(self):
        out = normalize_schema_prompt("p", _Schema())
        assert "```json" in out

    def test_legacy_schema_method(self):
        out = normalize_schema_prompt("p", _OldSchema())
        assert "legacy" in out

    def test_plain_class_without_model_json_schema(self):
        out = normalize_schema_prompt("p", _NoJsonSchema)
        assert '"type": "object"' in out

    def test_plain_dict_schema(self):
        out = normalize_schema_prompt("p", {"a": 1})
        assert '"a": 1' in out

    def test_unserializable_schema_falls_back_to_str(self):
        class Weird:
            def __repr__(self):
                return "<weird>"

        out = normalize_schema_prompt("p", Weird())
        assert "<weird>" in out


def _gw(**kw):
    kw.setdefault("providers", {})
    return ResilientLLMGateway(**kw)


class TestGatewayInit:
    def test_timeout_from_env(self, monkeypatch):
        monkeypatch.setenv("AUTONOVEL_LLM_CALL_TIMEOUT_SECONDS", "12.5")
        assert _gw().call_timeout_seconds == 12.5

    def test_timeout_default(self, monkeypatch):
        monkeypatch.delenv("AUTONOVEL_LLM_CALL_TIMEOUT_SECONDS", raising=False)
        assert _gw().call_timeout_seconds == 300.0

    def test_timeout_invalid_env(self, monkeypatch):
        monkeypatch.setenv("AUTONOVEL_LLM_CALL_TIMEOUT_SECONDS", "abc")
        assert _gw().call_timeout_seconds == 300.0

    def test_timeout_non_positive(self):
        assert _gw(call_timeout_seconds=-5).call_timeout_seconds == 300.0

    def test_backoff_clamped(self):
        g = _gw(backoff_base_seconds=-1, max_backoff_seconds=-1)
        assert g.backoff_base_seconds == 0.0
        assert g.max_backoff_seconds == 0.0

    def test_fallback_policy_object_passthrough(self):
        policy = FallbackPolicy({"x": ["y"]})
        g = _gw(fallback_policy=policy)
        assert g.fallback_policy is policy

    def test_fallback_policy_mapping_wrapped(self):
        g = _gw(fallback_policy={"x": ["y"]})
        assert g.fallback_policy.get_fallback_sequence("x") == ["y"]

    def test_failover_manager_singleton(self):
        a = _gw()._failover_manager
        b = _gw()._failover_manager
        assert a is b

    def test_failover_breaker_unknown_provider(self):
        g = _gw()
        assert g._failover_breaker_for("does-not-exist") is None


class TestCanonicalProvider:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Claude", "claude"),
            ("anthropic-large", "claude"),
            ("google-flash", "gemini"),
            ("my-ollama-box", "ollama"),
            ("vllm-local", "vllm"),
            ("mockit", "mock"),
            ("gpt-4o", "openai"),
            ("openrouter-x", "openai"),
            ("totally-unknown", "totally-unknown"),
        ],
    )
    def test_canonical(self, raw, expected):
        assert _gw()._canonical_provider(raw) == expected

    def test_registered_name_passthrough(self):
        g = _gw(providers={"weird_one": object()})
        assert g._canonical_provider("weird_one") == "weird_one"


class TestGetProvider:
    def test_from_mapping(self):
        sentinel = object()
        g = _gw(providers={"a": sentinel})
        assert g._get_provider("a") is sentinel

    def test_no_factory(self):
        assert _gw()._get_provider("a") is None

    def test_factory_get_provider(self):
        sentinel = object()
        g = _gw(provider_factory=type("F", (), {"get_provider": staticmethod(lambda n: sentinel)})())
        assert g._get_provider("a") is sentinel
        assert g.providers["a"] is sentinel

    def test_factory_get_provider_type_error_fallback(self):
        sentinel = object()
        g = _gw(provider_factory=type("F", (), {"get_client": staticmethod(lambda: sentinel)})())
        assert g._get_provider("a") is sentinel

    def test_factory_create_returns_none(self):
        g = _gw(provider_factory=type("F", (), {"create": staticmethod(lambda n: None)})())
        assert g._get_provider("a") is None

    def test_callable_factory(self):
        sentinel = object()
        g = _gw(provider_factory=lambda n: sentinel)
        assert g._get_provider("a") is sentinel

    def test_callable_factory_no_arg(self):
        sentinel = object()
        g = _gw(provider_factory=lambda: sentinel)
        assert g._get_provider("a") is sentinel


class TestGenerateFlow:
    async def test_mock_blocked_raises(self, monkeypatch):
        monkeypatch.setattr(rg, "_mock_allowed", lambda: False)
        mock = AsyncMock()
        mock.generate_text.return_value = "mocked"
        g = _gw(providers={"mock": mock}, fallback_policy={"mock": []})
        with pytest.raises(RuntimeError, match="Refusing to use the 'mock'"):
            await g.generate_text("p", primary_provider="mock")
        mock.generate_text.assert_not_awaited()

    async def test_circuit_open_raises(self):
        cb = LLMCircuitBreaker(failure_threshold=1, timeout_seconds=999)
        cb.record_failure("openai")
        g = _gw(providers={"openai": AsyncMock()}, circuit_breaker=cb, fallback_policy={"openai": []})
        with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
            await g.generate_text("p", primary_provider="openai")

    async def test_provider_unavailable_raises(self):
        g = _gw(fallback_policy={"openai": []})
        with pytest.raises(RuntimeError, match="unavailable"):
            await g.generate_text("p", primary_provider="openai")

    async def test_duplicate_candidates_skipped(self):
        calls = []

        def factory(name):
            def gen_text(prompt, **kw):
                calls.append(name)
                return f"{name}-ok"
            return gen_text

        g = _gw(provider_factory=factory, fallback_policy={"openai": ["gemini", "openai"]})
        out = await g.generate_text("p", primary_provider="openai")
        assert out == "openai-ok"
        assert calls == ["openai"]

    async def test_all_fail_raises_aggregate(self):
        bad1 = AsyncMock()
        bad1.generate_text.side_effect = RuntimeError("x")
        bad2 = AsyncMock()
        bad2.generate_text.side_effect = RuntimeError("y")
        g = _gw(providers={"openai": bad1, "gemini": bad2}, fallback_policy={"openai": ["gemini"]})
        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            await g.generate_text("p", primary_provider="openai")

    async def test_cancelled_error_propagates(self):
        bad = AsyncMock()
        bad.generate_text.side_effect = asyncio.CancelledError()
        g = _gw(providers={"openai": bad}, fallback_policy={"openai": []})
        with pytest.raises(asyncio.CancelledError):
            await g.generate_text("p", primary_provider="openai")

    async def test_generate_json_passes_schema(self):
        prov = AsyncMock()
        prov.generate_json.return_value = {"ok": True}
        g = _gw(providers={"openai": prov}, fallback_policy={"openai": []})
        out = await g.generate_json("p", response_schema=_Schema, primary_provider="openai")
        assert out == {"ok": True}
        kwargs = prov.generate_json.await_args.kwargs
        assert kwargs["response_schema"] is _Schema

    async def test_generate_text_response_schema_reinserted(self):
        prov = AsyncMock()
        prov.generate_text.return_value = "t"
        g = _gw(providers={"openai": prov}, fallback_policy={"openai": []})
        await g.generate_text("p", response_schema=_Schema, primary_provider="openai")
        assert prov.generate_text.await_args.kwargs["response_schema"] is _Schema

    async def test_status_and_reset(self):
        cb = LLMCircuitBreaker(failure_threshold=1, timeout_seconds=999)
        g = _gw(circuit_breaker=cb)
        cb.record_failure("openai")
        assert "openai" in g.status()
        g.reset("openai")
        assert cb.can_execute("openai")


class TestInvoke:
    async def test_callable_provider_used_directly(self):
        class CallableProvider:
            def __call__(self, prompt, system_instruction=None, temperature=0.0):
                return f"lambda:{prompt}"

        g = _gw()
        out = await g._invoke(CallableProvider(), "openai", "generate_text", "p", None, 0.1, {})
        assert out == "lambda:p"

    async def test_unexpected_keyword_retries_positionally(self):
        def gen_text(*args, **kwargs):
            if not args:
                raise TypeError("gen_text() got an unexpected keyword argument 'extra'")
            return "recovered"

        # Reports a signature without VAR_KEYWORD so kwargs are filtered out
        gen_text.__signature__ = inspect.Signature(
            [inspect.Parameter("foo", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        )
        g = _gw()
        out = await g._invoke(gen_text, "openai", "generate_text", "p", None, 0.1, {"extra": 1})
        assert out == "recovered"

    async def test_missing_method_raises(self):
        g = _gw()
        with pytest.raises(AttributeError):
            await g._invoke(object(), "openai", "generate_text", "p", None, 0.1, {})

    async def test_kwargs_filtered_for_explicit_signature(self):
        seen = {}

        def gen_text(prompt, system_instruction=None, temperature=0.0):
            seen.update(prompt=prompt, system_instruction=system_instruction, temperature=temperature)
            return "ok"

        g = _gw()
        out = await g._invoke(gen_text, "openai", "generate_text", "p", "sys", 0.9, {"unknown": 1})
        assert out == "ok"
        assert seen == {"prompt": "p", "system_instruction": "sys", "temperature": 0.9}

    async def test_model_name_and_temp_alias(self):
        seen = {}

        def gen_text(model_name, prompt, temp, response_format):
            seen.update(model_name=model_name, temp=temp, response_format=response_format)
            return "ok"

        g = _gw()
        await g._invoke(gen_text, "gemini", "generate_text", "p", None, 0.5, {"response_schema": _Schema})
        assert seen["model_name"] == "gemini"
        assert seen["temp"] == 0.5
        assert seen["response_format"] == {"type": "json_object"}

    async def test_context_injected_when_absent(self):
        seen = {}

        def gen_text(prompt, context=None):
            seen["context"] = context
            return "ok"

        g = _gw()
        await g._invoke(gen_text, "openai", "generate_text", "p", None, 0.1, {})
        assert isinstance(seen["context"], float)

    async def test_system_prompt_kwarg_used(self):
        seen = {}

        def gen_text(prompt, system_prompt=None):
            seen["system_prompt"] = system_prompt
            return "ok"

        g = _gw()
        await g._invoke(gen_text, "openai", "generate_text", "p", None, 0.1, {"system_prompt": "S"})
        assert seen["system_prompt"] == "S"

    async def test_var_keyword_receives_all(self):
        seen = {}

        def gen_text(prompt, **kw):
            seen.update(kw)
            return "ok"

        g = _gw()
        await g._invoke(gen_text, "openai", "generate_text", "p", None, 0.1, {"extra": 5})
        assert seen["extra"] == 5

    async def test_unsignaturable_method_uses_positional_call(self):
        calls = []

        def provider(prompt, name, system, temp, **kw):
            calls.append((prompt, name, system, temp))
            return "positional"

        # 実際の呼び出しは inspect.signature 失敗経路を通る
        import inspect as _inspect

        original = _inspect.signature
        try:
            _inspect.signature = lambda obj: (_ for _ in ()).throw(ValueError("boom"))
            g = _gw()
            out = await g._invoke(provider, "openai", "generate_text", "p", "s", 0.2, {})
        finally:
            _inspect.signature = original
        assert out == "positional"
        assert calls == [("p", "openai", "s", 0.2)]

    async def test_response_format_explicit(self):
        seen = {}

        def gen_text(prompt, response_format):
            seen["response_format"] = response_format
            return "ok"

        g = _gw()
        await g._invoke(gen_text, "openai", "generate_text", "p", None, 0.1, {"response_format": "json"})
        assert seen["response_format"] == "json"

    async def test_timeout_raises_timeout_error(self):
        class Slow:
            def generate_text(self, prompt, **kw):
                async def _slow():
                    await asyncio.sleep(5)
                return _slow()

        g = _gw(call_timeout_seconds=0.01)
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await g._invoke(Slow(), "openai", "generate_text", "p", None, 0.1, {})


class TestBackoffAndRateLimit:
    async def test_retry_after_attribute(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        class Err(Exception):
            retry_after = 5.0

        # サーバー指定の Retry-After は max_backoff_seconds ではなく
        # max_retry_after_seconds で丸められる（レート制限ウィンドウが解けるまで待つ）。
        g = _gw(sleep=sleep, max_backoff_seconds=3.0, max_retry_after_seconds=120.0)
        await g._backoff(Err(), 0)
        assert slept == [5.0]

    async def test_retry_after_capped_by_max_retry_after_seconds(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        class Err(Exception):
            retry_after = 3600.0

        # 巨大でも max_retry_after_seconds で頭打ちになる（無限待機はしない）
        g = _gw(sleep=sleep, max_backoff_seconds=2.0, max_retry_after_seconds=30.0)
        await g._backoff(Err(), 0)
        assert slept == [30.0]

    async def test_derived_backoff_capped_by_max_backoff_seconds(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        # 導出バックオフ（Retry-After 無し）は従来どおり max_backoff_seconds が上限
        g = _gw(sleep=sleep, backoff_base_seconds=2.0, max_backoff_seconds=3.0)
        await g._backoff(Exception("boom"), 5)
        assert slept == [3.0]

    async def test_retry_after_from_response(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        class Resp:
            retry_after = 0.5

        class Err(Exception):
            response = Resp()

        g = _gw(sleep=sleep)
        await g._backoff(Err(), 0)
        assert slept == [0.5]

    async def test_retry_after_parsed_from_message(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        g = _gw(sleep=sleep, max_backoff_seconds=100.0)
        await g._backoff(Exception("Retry-After: 7"), 0)
        assert slept == [7.0]

    async def test_default_exponential(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        g = _gw(sleep=sleep, backoff_base_seconds=0.1, max_backoff_seconds=10.0)
        await g._backoff(Exception("boom"), 2)
        assert slept == [0.4]

    async def test_zero_retry_after_no_sleep(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        class Err(Exception):
            retry_after = 0

        g = _gw(sleep=sleep)
        await g._backoff(Err(), 0)
        assert slept == []

    @pytest.mark.parametrize(
        "err,expected",
        [
            (type("RateLimitError", (Exception,), {})(), True),
            (type("ResourceExhausted", (Exception,), {})(), True),
            (Exception("429 too many requests"), True),
            (Exception("plain"), False),
        ],
    )
    def test_is_rate_limit_error(self, err, expected):
        assert ResilientLLMGateway._is_rate_limit_error(err) is expected

    def test_is_rate_limit_status_code(self):
        class Err(Exception):
            status_code = 429

        assert ResilientLLMGateway._is_rate_limit_error(Err()) is True

    def test_is_rate_limit_response_status(self):
        class Resp:
            status_code = 429

        class Err(Exception):
            response = Resp()

        assert ResilientLLMGateway._is_rate_limit_error(Err()) is True

    def test_record_failover_counter(self):
        ResilientLLMGateway._record_failover("a", "b", "error")
        assert rg.llm_failover_total is rg.failover_counter

    def test_next_candidate(self):
        assert ResilientLLMGateway._next_candidate(["a", "b", "c"], 0, set()) == "b"
        assert ResilientLLMGateway._next_candidate(["a", "b"], 0, {"b"}) is None
        assert ResilientLLMGateway._next_candidate(["a"], 5, set()) is None
