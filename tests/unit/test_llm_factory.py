"""LLM ファクトリモジュールのユニットテスト。"""
from __future__ import annotations

import pytest

from src.backend.config import settings
from src.services.llm.factory import get_llm_adapter
from src.services.llm.mock_adapter import MockLLMAdapter


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch):
    """各テストでLLM 関連環境変数をクリアし、独立性を担保する。

    ファクトリのテスト環境ショートカット (APP_ENV=testing で MockLLMAdapter を返す)
    を無効化し、各プロバイダの分岐を実際に検証できるようにする。
    """
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", None)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.delenv("APP_ENV", raising=False)
    yield


def test_get_llm_adapter_gemini_with_key(monkeypatch):
    """GeminiプロバイダーでAPIキーあり。"""
    settings.GEMINI_API_KEY = "test-key-123"
    adapter = get_llm_adapter(provider="gemini")
    assert adapter.__class__.__name__ == "GeminiAdapter"


def test_get_llm_adapter_gemini_without_key_raises(monkeypatch):
    """GeminiプロバイダーでAPIキーなしはRuntimeError送出（フェイルFAST）。"""
    settings.GEMINI_API_KEY = None
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        get_llm_adapter(provider="gemini")


def test_get_llm_adapter_openai_with_key(monkeypatch):
    """OpenAIプロバイダーでAPIキーあり。"""
    settings.OPENAI_API_KEY = "sk-test-123"
    adapter = get_llm_adapter(provider="openai")
    assert adapter.__class__.__name__ == "OpenAIAdapter"


def test_get_llm_adapter_openai_without_key_raises(monkeypatch):
    """OpenAIプロバイダーでキー/BASE_URLなしはRuntimeError送出。"""
    settings.OPENAI_API_KEY = None
    settings.OPENAI_BASE_URL = None
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_llm_adapter(provider="openai")


def test_get_llm_adapter_openai_with_base_url_only(monkeypatch):
    """OpenAIプロバイダーで BASE_URL のみ設定されていれば通る（OpenRouter等）。"""
    settings.OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
    settings.OPENAI_API_KEY = None
    adapter = get_llm_adapter(provider="openai")
    assert adapter.__class__.__name__ == "OpenAIAdapter"


def test_get_llm_adapter_claude_with_key(monkeypatch):
    settings.ANTHROPIC_API_KEY = "sk-ant-test-123"
    adapter = get_llm_adapter(provider="claude")
    assert adapter.__class__.__name__ == "ClaudeAdapter"


def test_get_llm_adapter_claude_without_key_raises(monkeypatch):
    settings.ANTHROPIC_API_KEY = None
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_llm_adapter(provider="claude")


def test_get_llm_adapter_default_provider(monkeypatch):
    settings.LLM_PROVIDER = "openai"
    settings.OPENAI_API_KEY = "sk-default-123"
    adapter = get_llm_adapter()
    assert adapter.__class__.__name__ == "OpenAIAdapter"


def test_get_llm_adapter_unknown_provider_raises():
    """未知のプロバイダは例外を送出する (モックへの無条件フォールバック禁止)。

    旧実装は WARNING のみで MockLLMAdapter を返したため、タイプミス等で
    モックの固定本文が本物の生成結果として保存され得ていた。
    """
    with pytest.raises(RuntimeError, match="未実装"):
        get_llm_adapter(provider="unknown")


def test_get_llm_adapter_explicit_mock_still_works():
    """明示的な provider='mock' 指定は引き続きモックを返す。"""
    adapter = get_llm_adapter(provider="mock")
    assert isinstance(adapter, MockLLMAdapter)


def test_get_llm_adapter_ollama(monkeypatch):
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    settings.OLLAMA_MODEL = "llama3.1"
    adapter = get_llm_adapter(provider="ollama")
    assert adapter.__class__.__name__ == "OllamaAdapter"


def test_get_llm_adapter_vllm(monkeypatch):
    settings.VLLM_BASE_URL = "http://localhost:8000"
    settings.VLLM_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
    adapter = get_llm_adapter(provider="vllm")
    assert adapter.__class__.__name__ == "VLLMAdapter"
