"""services/llm: アダプタ・ファクトリ・再試行・ブローカーのカバレッジ。"""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.services.llm.gemini_adapter as gemini_mod
from src.services.llm.base import (
    PLACEHOLDER_API_KEY,
    BaseLLMAdapter,
    LLMConfigurationError,
    ensure_api_key_configured,
    is_placeholder_api_key,
)
from src.services.llm.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
)
from src.services.llm.claude_adapter import ClaudeAdapter
from src.services.llm.factory import IMPLEMENTED_PROVIDERS, get_llm_adapter
from src.services.llm.mock_adapter import MockLLMAdapter
from src.services.llm.ollama_adapter import OllamaAdapter
from src.services.llm.openai_adapter import OpenAIAdapter
from src.services.llm.prompt_cache_builder import PromptCacheBuilder
from src.services.llm.provider_failover import ProviderFailoverManager
from src.services.llm.retry import with_retry
from src.services.llm.vllm_adapter import VLLMAdapter


# --------------------------------------------------------------------------
# base.py
# --------------------------------------------------------------------------
class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        async def gen():
            for i in self._items:
                yield i
        return gen()


@pytest.fixture
def always_warn():
    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("always")
        yield


def test_placeholder_helpers():
    assert is_placeholder_api_key(None) is True
    assert is_placeholder_api_key("") is True
    assert is_placeholder_api_key(PLACEHOLDER_API_KEY) is True
    assert is_placeholder_api_key("DUMMY") is True
    assert is_placeholder_api_key("dummy-key") is True
    assert is_placeholder_api_key("real-key") is False
    assert ensure_api_key_configured("real", "P", "ENV") == "real"
    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        ensure_api_key_configured(None, "Gemini", "GEMINI_API_KEY")


async def test_base_adapter_abstract_hooks(always_warn):
    class Impl(BaseLLMAdapter):
        async def generate_text(self, prompt, system_prompt=None, max_tokens=2000,
                               temperature=0.7, response_format=None, **kw):
            return "ok"

        async def stream_text(self, prompt, system_prompt=None, max_tokens=2000,
                              temperature=0.7, **kw):
            yield "a"

    assert await Impl().generate_text("p") == "ok"
    assert Impl().cancel() is None
    assert [c async for c in Impl().stream_text("p")] == ["a"]

    with pytest.warns(DeprecationWarning):
        with pytest.raises(NotImplementedError):
            await BaseLLMAdapter.generate_text(Impl(), "p")
    with pytest.warns(DeprecationWarning):
        gen = BaseLLMAdapter.stream_text(Impl(), "p")
        with pytest.raises(NotImplementedError):
            await gen.__anext__()


def test_base_adapter_sync_generate_no_loop(always_warn):
    class Impl(BaseLLMAdapter):
        async def generate_text(self, prompt, system_prompt=None, max_tokens=2000,
                               temperature=0.7, response_format=None, **kw):
            return "sync-ok"

        async def stream_text(self, prompt, system_prompt=None, max_tokens=2000,
                              temperature=0.7, **kw):
            yield ""

    with pytest.warns(DeprecationWarning):
        assert Impl().generate("p") == "sync-ok"


async def test_base_adapter_sync_generate_inside_loop(always_warn):
    class Impl(BaseLLMAdapter):
        async def generate_text(self, prompt, system_prompt=None, max_tokens=2000,
                               temperature=0.7, response_format=None, **kw):
            return "threaded"

        async def stream_text(self, prompt, system_prompt=None, max_tokens=2000,
                              temperature=0.7, **kw):
            yield ""

    with pytest.warns(DeprecationWarning):
        assert Impl().generate("p") == "threaded"


# --------------------------------------------------------------------------
# retry.py
# --------------------------------------------------------------------------
async def test_with_retry_success_first_try():
    async def fn():
        return "v"

    assert await with_retry(fn) == "v"


async def test_with_retry_then_success(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("nope")
        return "ok"

    assert await with_retry(fn, max_retries=3, initial_delay=0.0) == "ok"
    assert calls["n"] == 3


async def test_with_retry_raises_last(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    async def fn():
        raise KeyError("final")

    with pytest.raises(KeyError):
        await with_retry(fn, max_retries=2, initial_delay=0.0)


async def test_with_retry_zero_retries_hits_runtime_error():
    async def fn():
        raise AssertionError("never")

    with pytest.raises(RuntimeError, match="exited unexpectedly"):
        await with_retry(fn, max_retries=0)


# --------------------------------------------------------------------------
# circuit_breaker.py / provider_failover.py
# --------------------------------------------------------------------------
def test_circuit_breaker_lifecycle():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0, provider_name="openai")
    assert cb.can_execute() is True
    cb.record_success()
    assert cb.failure_count == 0
    cb.record_failure(error=RuntimeError("x"))
    assert cb.failure_count == 1
    cb.record_failure("openai")
    assert cb.can_execute() is False


def test_circuit_breaker_with_injected_underlying():
    underlying = MagicMock()
    underlying.can_execute.return_value = True
    underlying.get_state.return_value = SimpleNamespace(state="closed", failure_count=7)
    cb = CircuitBreaker(underlying=underlying, provider_name="claude")
    assert cb.failure_count == 7
    assert cb.state == "closed"
    cb.record_success()
    underlying.record_success.assert_called_once_with("claude")
    cb.record_failure(error="e")
    underlying.record_failure.assert_called_once_with("claude", "e")
    assert cb.can_execute() is True


async def test_provider_failover_success_and_fallback():
    mgr = ProviderFailoverManager()
    assert set(mgr.breakers) == {"gemini", "openai", "claude"}

    async def ok():
        return 1

    assert await mgr.execute_with_fallback("openai", "gemini", ok, ok) == (1, "openai")

    async def bad():
        raise RuntimeError("x")

    assert await mgr.execute_with_fallback("openai", "gemini", bad, ok) == (1, "gemini")


async def test_provider_failover_unknown_provider():
    mgr = ProviderFailoverManager()

    async def ok():
        return "u"

    assert await mgr.execute_with_fallback("unknown", "gemini", ok, ok) == ("u", "unknown")


async def test_provider_failover_all_circuits_open():
    mgr = ProviderFailoverManager()
    for _ in range(3):
        mgr.breakers["openai"].record_failure()
        mgr.breakers["gemini"].record_failure()

    async def ok():
        return 1

    with pytest.raises(CircuitBreakerOpenException):
        await mgr.execute_with_fallback("openai", "gemini", ok, ok)


async def test_provider_failover_fallback_raises():
    mgr = ProviderFailoverManager()

    async def bad():
        raise ValueError("both")

    with pytest.raises(ValueError):
        await mgr.execute_with_fallback("openai", "gemini", bad, bad)
    assert mgr.breakers["gemini"].failure_count == 1


# --------------------------------------------------------------------------
# factory.py
# --------------------------------------------------------------------------
@pytest.fixture
def prod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")


def test_factory_testing_env_returns_mock(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    assert isinstance(get_llm_adapter("openai", api_key="k"), MockLLMAdapter)


def test_factory_unimplemented_falls_back(prod):
    adapter = get_llm_adapter("unknown-provider")
    assert isinstance(adapter, MockLLMAdapter)


def test_factory_mock(prod):
    assert isinstance(get_llm_adapter("mock"), MockLLMAdapter)


def test_factory_gemini(prod, monkeypatch):
    monkeypatch.setattr("src.services.llm.factory.settings", SimpleNamespace(
        LLM_PROVIDER="gemini", GEMINI_API_KEY="", GEMINI_MODEL="m",
    ))
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        get_llm_adapter("gemini")
    a = get_llm_adapter("gemini", api_key="k", model_name="mm")
    assert isinstance(a, gemini_mod.GeminiAdapter)
    assert a.model_name == "mm"


def test_factory_openai(prod, monkeypatch):
    monkeypatch.setattr("src.services.llm.factory.settings", SimpleNamespace(
        LLM_PROVIDER="openai", OPENAI_API_KEY="", OPENAI_BASE_URL="", OPENAI_MODEL="m",
    ))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_llm_adapter("openai")
    a = get_llm_adapter("openai", base_url="http://x")
    assert isinstance(a, OpenAIAdapter)
    assert a.base_url == "http://x"


def test_factory_openrouter(prod, monkeypatch):
    monkeypatch.setattr("src.services.llm.factory.settings", SimpleNamespace(
        LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="", OPENAI_API_KEY="k2",
        OPENROUTER_MODEL="rm", OPENROUTER_BASE_URL="http://r",
    ))
    a = get_llm_adapter("openrouter")
    assert a.model == "rm"
    assert a.base_url == "http://r"
    monkeypatch.setattr("src.services.llm.factory.settings", SimpleNamespace(
        LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="", OPENAI_API_KEY="",
        OPENROUTER_MODEL="rm", OPENROUTER_BASE_URL="http://r",
    ))
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        get_llm_adapter("openrouter")


def test_factory_claude_ollama_vllm(prod, monkeypatch):
    monkeypatch.setattr("src.services.llm.factory.settings", SimpleNamespace(
        LLM_PROVIDER="claude", ANTHROPIC_API_KEY="", ANTHROPIC_MODEL="cm",
        OLLAMA_BASE_URL="http://o", OLLAMA_MODEL="om",
        VLLM_BASE_URL="http://v", VLLM_MODEL="vm",
    ))
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_llm_adapter("claude")
    assert isinstance(get_llm_adapter("claude", api_key="k"), ClaudeAdapter)
    assert isinstance(get_llm_adapter("ollama"), OllamaAdapter)
    assert isinstance(get_llm_adapter("vllm"), VLLMAdapter)
    assert "vllm" in IMPLEMENTED_PROVIDERS


# --------------------------------------------------------------------------
# mock_adapter.py
# --------------------------------------------------------------------------
async def test_mock_adapter_text_and_json():
    a = MockLLMAdapter()
    assert "アルト" in await a.generate_text("p")
    js = await a.generate_text("p", response_format={"type": "json_object"})
    assert "entities" in js
    js2 = await a.generate_text("p", response_format={"type": "json_schema"})
    assert "relationships" in js2
    assert "not-json" not in await a.generate_text("p", response_format={"type": "other"})


async def test_mock_adapter_stream_and_cancel():
    a = MockLLMAdapter()
    chunks = [c async for c in a.stream_text("p", stream_delay_ms=0)]
    assert len(chunks) == 8
    assert a._cancelled is False
    a.cancel()
    assert a._cancelled is True
    with pytest.raises(asyncio.CancelledError):
        [c async for c in a.stream_text("p", stream_delay_ms=0)]


# --------------------------------------------------------------------------
# openai / ollama / vllm adapters
# --------------------------------------------------------------------------
def _completion(content="hi"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _stream_chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def _install_client(adapter):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_completion())
    adapter.client = client
    return client


@pytest.mark.parametrize("cls", [OpenAIAdapter, OllamaAdapter, VLLMAdapter])
async def test_openai_compatible_generate(cls):
    a = cls()
    client = _install_client(a)
    out = await a.generate_text("p", system_prompt="s", response_format={"type": "json_object"})
    assert out == "hi"
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("cls", [OpenAIAdapter, OllamaAdapter, VLLMAdapter])
async def test_openai_compatible_stream(cls):
    a = cls()
    client = MagicMock()

    async def create(**kw):
        return _AsyncIter([_stream_chunk("a"), SimpleNamespace(choices=[]), _stream_chunk("b")])

    client.chat.completions.create = create
    a.client = client
    out = [c async for c in a.stream_text("p", system_prompt="s")]
    assert out == ["a", "b"]


@pytest.mark.parametrize("cls", [OpenAIAdapter, OllamaAdapter, VLLMAdapter])
def test_openai_compatible_lazy_client(cls, monkeypatch):
    a = cls()
    fake_module = types.ModuleType("openai")
    created = {}

    class AsyncOpenAI:
        def __init__(self, **kw):
            created.update(kw)

    fake_module.AsyncOpenAI = AsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    assert a.client is a.client
    assert created


def test_openai_placeholder_key_warns(caplog):
    with caplog.at_level("WARNING"):
        a = OpenAIAdapter(api_key=PLACEHOLDER_API_KEY, base_url="http://x", model="m")
    assert "without a real API key" in caplog.text
    assert a.model == "m"


# --------------------------------------------------------------------------
# claude adapter
# --------------------------------------------------------------------------
def _claude_client():
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text="claude-out")])
    )

    stream = MagicMock()
    stream.text_stream = _AsyncIter(["a", "b"])
    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=stream)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)
    client.messages.stream = AsyncMock(return_value=stream_ctx)
    return client


async def test_claude_generate_with_and_without_system():
    a = ClaudeAdapter(api_key="k", model_name="m")
    a._client = _claude_client()
    assert await a.generate_text("p", system_prompt="sys") == "claude-out"
    assert a._client.messages.create.await_args.kwargs["system"] == "sys"
    assert await a.generate_text("p") == "claude-out"
    assert a._client.messages.create.await_args.kwargs["system"] is None


async def test_claude_stream():
    a = ClaudeAdapter(api_key="k")
    a._client = _claude_client()
    assert [c async for c in a.stream_text("p", system_prompt="s")] == ["a", "b"]


def test_claude_get_client(monkeypatch):
    a = ClaudeAdapter(api_key="k")
    fake = types.ModuleType("anthropic")
    fake.AsyncAnthropic = lambda api_key: ("client", api_key)
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    assert a._get_client() == ("client", "k")


# --------------------------------------------------------------------------
# gemini adapter
# --------------------------------------------------------------------------
def _install_genai(monkeypatch):
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=SimpleNamespace(text="g-out"))
    client.aio.models.generate_content_stream = AsyncMock(
        return_value=_AsyncIter([SimpleNamespace(text="g1"), SimpleNamespace(text=None), SimpleNamespace(text="g2")])
    )
    fake = types.ModuleType("google.genai")
    fake.Client = lambda api_key: client
    types_mod = types.ModuleType("google.genai.types")
    types_mod.GenerateContentConfig = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.genai", fake)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)
    return client


async def test_gemini_generate_and_stream(monkeypatch):
    client = _install_genai(monkeypatch)
    a = gemini_mod.GeminiAdapter(api_key="k", model_name="gm")
    assert await a.generate_text("p", system_prompt="s") == "g-out"
    kwargs = client.aio.models.generate_content.await_args.kwargs
    assert kwargs["contents"] == "s\n\np"
    assert "response_mime_type" not in kwargs["config"]
    await a.generate_text("p", response_format={"type": "json_object"})
    assert client.aio.models.generate_content.await_args.kwargs["config"]["response_mime_type"] == "application/json"
    assert [c async for c in a.stream_text("p")] == ["g1", "g2"]


def test_gemini_module_getattr(monkeypatch):
    _install_genai(monkeypatch)
    assert gemini_mod.types is not None
    assert gemini_mod.genai is not None
    with pytest.raises(AttributeError):
        gemini_mod.nope


def test_gemini_client_requires_key(monkeypatch):
    monkeypatch.setattr("src.services.llm.gemini_adapter.settings", SimpleNamespace(
        GEMINI_API_KEY="", GEMINI_MODEL="gm",
    ))
    a = gemini_mod.GeminiAdapter()
    assert a.api_key == PLACEHOLDER_API_KEY
    with pytest.raises(LLMConfigurationError):
        a._get_client()


def test_gemini_client_constructed(monkeypatch):
    _install_genai(monkeypatch)
    a = gemini_mod.GeminiAdapter(api_key="k")
    assert a._get_client() is a._get_client()


# --------------------------------------------------------------------------
# prompt_cache_builder.py
# --------------------------------------------------------------------------
async def test_prompt_cache_builder_without_services():
    b = PromptCacheBuilder()
    assert await b.build_world_bible_cache_block(1) == {"type": "text", "text": ""}
    assert await b.build_character_cache_block(1) == {"type": "text", "text": ""}
    assert b.build_combined_cache_block({"a": 1}, {"b": 2}) == [{"a": 1}, {"b": 2}]


async def test_prompt_cache_builder_with_services():
    book = MagicMock()
    book.get_world_bible = AsyncMock(return_value="bible")
    char = MagicMock()
    char.get_all_characters = AsyncMock(
        return_value=[SimpleNamespace(name="A", description="d1"), SimpleNamespace(name="B", description="d2")]
    )
    b = PromptCacheBuilder(book, char)
    assert (await b.build_world_bible_cache_block(3))["text"] == "bible"
    assert (await b.build_character_cache_block(3))["text"] == "A: d1\nB: d2"
