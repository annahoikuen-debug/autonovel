"""src/infrastructure/external/anthropic_client.py の単体テスト。"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# anthropic パッケージが未インストール環境でもインポート可能にするため、
# ダミーモジュールを事前登録してから factory をインポートする。
for _mod in ("anthropic",):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from src.infrastructure.external.anthropic_client import AnthropicClient


class TestAnthropicClient:
    """AnthropicClient クラスの単体テスト。"""

    def test_init_without_anthropic_sdk(self):
        """anthropic SDK 未インストール環境では client が None になること。"""
        with patch(
            "src.infrastructure.external.anthropic_client.anthropic", None
        ):
            client = AnthropicClient(api_key="test-key")
            assert client.client is None
            assert client.cache_builder is not None

    def test_init_with_anthropic_sdk(self):
        """anthropic SDK インストール済み環境では client が生成されること。"""
        mock_anthropic = MagicMock()
        mock_client_instance = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client_instance

        with patch(
            "src.infrastructure.external.anthropic_client.anthropic", mock_anthropic
        ):
            client = AnthropicClient(api_key="test-key")
            mock_anthropic.Anthropic.assert_called_once_with(api_key="test-key")
            assert client.client is mock_client_instance
            assert client.cache_builder is not None

    def test_cache_builder_is_prompt_cache_builder(self):
        """cache_builder が PromptCacheBuilder のインスタンスであること。"""
        from src.infrastructure.external.prompt_cache_builder import (
            PromptCacheBuilder,
        )

        with patch(
            "src.infrastructure.external.anthropic_client.anthropic", None
        ):
            client = AnthropicClient(api_key="test-key")
            assert isinstance(client.cache_builder, PromptCacheBuilder)


class TestAnthropicClientGenerate:
    """AnthropicClient.generate_with_caching の単体テスト。"""

    @pytest.mark.asyncio
    async def test_generate_with_caching_no_client(self):
        """client が None のとき、generate_with_caching は AttributeError を送出すること。"""
        with patch(
            "src.infrastructure.external.anthropic_client.anthropic", None
        ):
            client = AnthropicClient(api_key="test-key")

            with pytest.raises(AttributeError):
                await client.generate_with_caching(
                    book_id=1, user_prompt="Hello"
                )

    @pytest.mark.asyncio
    async def test_generate_with_caching_with_mock_client(self):
        """client がモックのとき、generate_with_caching が正常に動作すること。"""
        from src.infrastructure.external.prompt_cache_builder import (
            PromptCacheBuilder,
        )

        mock_anthropic = MagicMock()
        mock_client_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="生成されたテキスト")]
        mock_response.usage = {"input_tokens": 100, "output_tokens": 50}
        mock_client_instance.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client_instance

        with patch(
            "src.infrastructure.external.anthropic_client.anthropic", mock_anthropic
        ):
            client = AnthropicClient(api_key="test-key")

            # cache_builder の build_world_bible_cache_block / build_character_cache_block をモック
            client.cache_builder.build_world_bible_cache_block = AsyncMock(
                return_value={"type": "text", "text": "world bible"}
            )
            client.cache_builder.build_character_cache_block = AsyncMock(
                return_value={"type": "text", "text": "characters"}
            )

            result = await client.generate_with_caching(
                book_id=1, user_prompt="Write a story"
            )

            assert result["content"] == "生成されたテキスト"
            assert "cache_info" in result
            assert "usage" in result
            mock_client_instance.messages.create.assert_called_once()
