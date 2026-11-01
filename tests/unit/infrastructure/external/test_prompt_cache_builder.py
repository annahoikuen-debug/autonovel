"""src/infrastructure/external/prompt_cache_builder.py の単体テスト。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.infrastructure.external.prompt_cache_builder import PromptCacheBuilder


class TestPromptCacheBuilder:
    """PromptCacheBuilder クラスの単体テスト。"""

    def test_init_defaults(self):
        """book_service / character_service が None で初期化できること。"""
        builder = PromptCacheBuilder()
        assert builder.book_service is None
        assert builder.character_service is None

    def test_init_with_services(self):
        """book_service / character_service を指定して初期化できること。"""
        book_svc = object()
        char_svc = object()
        builder = PromptCacheBuilder(book_service=book_svc, character_service=char_svc)
        assert builder.book_service is book_svc
        assert builder.character_service is char_svc

    @pytest.mark.asyncio
    async def test_build_world_bible_cache_block_no_service(self):
        """book_service 未設定時は空文字の world bible ブロックを返すこと。"""
        builder = PromptCacheBuilder()
        result = await builder.build_world_bible_cache_block(book_id=1)

        assert result["type"] == "text"
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_build_world_bible_cache_block_with_service(self):
        """book_service が設定済み時は get_world_bible の結果を返すこと。"""
        mock_book_service = AsyncMock()
        mock_book_service.get_world_bible.return_value = "世界設定：剣と魔法の世界"

        builder = PromptCacheBuilder(book_service=mock_book_service)
        result = await builder.build_world_bible_cache_block(book_id=42)

        mock_book_service.get_world_bible.assert_awaited_once_with(42)
        assert result["type"] == "text"
        assert result["text"] == "世界設定：剣と魔法の世界"

    @pytest.mark.asyncio
    async def test_build_character_cache_block_no_service(self):
        """character_service 未設定時は空リストの character ブロックを返すこと。"""
        builder = PromptCacheBuilder()
        result = await builder.build_character_cache_block(book_id=1)

        assert result["type"] == "text"
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_build_character_cache_block_with_service(self):
        """character_service が設定済み時は get_all_characters の結果を返すこと。"""
        mock_char_service = AsyncMock()
        mock_char_service.get_all_characters.return_value = [
            type("Char", (), {"name": "アルト", "description": "熱血の主人公"})(),
            type("Char", (), {"name": "アイリス", "description": "クールな魔導師"})(),
        ]

        builder = PromptCacheBuilder(character_service=mock_char_service)
        result = await builder.build_character_cache_block(book_id=7)

        mock_char_service.get_all_characters.assert_awaited_once_with(7)
        assert result["type"] == "text"
        text = result["text"]
        assert "アルト" in text
        assert "アイリス" in text

    def test_build_combined_cache_block(self):
        """build_combined_cache_block は2つのブロックを含むリストを返すこと。"""
        builder = PromptCacheBuilder()
        world_block = {"type": "text", "text": "world bible"}
        char_block = {"type": "text", "text": "characters"}

        result = builder.build_combined_cache_block(world_block, char_block)

        assert result == [world_block, char_block]
        assert len(result) == 2
