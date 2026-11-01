"""src/core/llm/factory.py の単体テスト。"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# オプション依存 (anthropic, google.generativeai, ollama 等) が
# テスト環境にインストールされていない場合に備えて、ダミーモジュールを
# 登録してから factory をインポートする。
for _mod in (
    "anthropic",
    "anthropic.types",
    "google",
    "google.genai",
    "ollama",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from src.core.llm.factory import create_unified_llm_client


class TestCreateUnifiedLLMClient:
    """create_unified_llm_client の単体テスト。"""

    def test_create_mock_client(self):
        """'mock' プロバイダで UnifiedMockLLMClient が生成されること。"""
        client = create_unified_llm_client("mock")
        assert client is not None
        from src.core.llm.adapters.mock_unified_client import (
            UnifiedMockLLMClient,
        )

        assert isinstance(client, UnifiedMockLLMClient)

    def test_create_openai_client(self):
        """'openai' プロバイダで OpenAIUnifiedClient が生成されること。"""
        with patch(
            "src.backend.config.settings.OPENAI_API_KEY", "sk-test-openai-key"
        ), patch(
            "src.backend.config.settings.OPENAI_BASE_URL", None
        ):
            client = create_unified_llm_client("openai")
            assert client is not None
            from src.core.llm.adapters.openai_unified_client import (
                OpenAIUnifiedClient,
            )

            assert isinstance(client, OpenAIUnifiedClient)

    def test_create_claude_client(self):
        """'claude' プロバイダで ClaudeUnifiedClient が生成されること。"""
        with patch(
            "src.backend.config.settings.ANTHROPIC_API_KEY", "sk-ant-test-key"
        ), patch(
            "src.backend.config.settings.ANTHROPIC_MODEL", "claude-3-sonnet"
        ):
            client = create_unified_llm_client("claude")
            assert client is not None
            from src.core.llm.adapters.claude_unified_client import (
                ClaudeUnifiedClient,
            )

            assert isinstance(client, ClaudeUnifiedClient)

    def test_create_gemini_client(self):
        """'gemini' プロバイダで GeminiUnifiedClient が生成されること。"""
        with patch(
            "src.backend.config.settings.GEMINI_API_KEY", "AI-test-gemini-key"
        ), patch(
            "src.backend.config.settings.GEMINI_MODEL", "gemini-pro"
        ):
            client = create_unified_llm_client("gemini")
            assert client is not None
            from src.core.llm.adapters.gemini_unified_client import (
                GeminiUnifiedClient,
            )

            assert isinstance(client, GeminiUnifiedClient)

    def test_create_ollama_client(self):
        """'ollama' プロバイダで OllamaUnifiedClient が生成されること。"""
        client = create_unified_llm_client("ollama")
        assert client is not None
        from src.core.llm.adapters.ollama_unified_client import (
            OllamaUnifiedClient,
        )

        assert isinstance(client, OllamaUnifiedClient)

    def test_create_vllm_client(self):
        """'vllm' プロバイダで OllamaUnifiedClient が生成されること。"""
        client = create_unified_llm_client("vllm")
        assert client is not None
        from src.core.llm.adapters.ollama_unified_client import (
            OllamaUnifiedClient,
        )

        assert isinstance(client, OllamaUnifiedClient)

    def test_unknown_provider_raises_value_error(self):
        """未知プロバイダでは ValueError が送出されること。"""
        with pytest.raises(ValueError, match="Unknown provider"):
            create_unified_llm_client("unknown-provider")

    def test_provider_name_is_case_insensitive(self):
        """プロバイダ名は大文字小文字を区別しないこと。"""
        client = create_unified_llm_client("MOCK")
        from src.core.llm.adapters.mock_unified_client import (
            UnifiedMockLLMClient,
        )

        assert isinstance(client, UnifiedMockLLMClient)

        client = create_unified_llm_client("Mock")
        assert isinstance(client, UnifiedMockLLMClient)
