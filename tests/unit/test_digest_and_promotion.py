import pytest
from unittest.mock import AsyncMock, patch

from src.services.digest_service import CHAPTER_MAX_LENGTH, generate_suggestions, process_chapter


def test_process_chapter():
    """process_chapter の文字数トリムと省略記号付与の検証。"""
    short_text = "短い章本文です。"
    assert process_chapter(short_text) == short_text

    long_text = "あ" * 2000
    processed = process_chapter(long_text)
    assert len(processed) <= 1505
    assert processed.endswith("...")


def test_process_chapter_under_max():
    """文字数がMAX未満の場合、元の文字列がそのまま返る。"""
    short_text = "あ" * 100
    processed = process_chapter(short_text)
    assert processed == short_text


@pytest.mark.asyncio
async def test_generate_suggestions():
    """章本文からの執筆サジェスチョン生成検証。"""
    suggestions_empty = await generate_suggestions("")
    assert len(suggestions_empty) >= 1

    with patch(
        "src.services.digest_service.LLMService.generate",
        new_callable=AsyncMock,
        return_value="主人公は新たな街に到着した。冒険が始まる。",
    ):
        suggestions_filled = await generate_suggestions("主人公は新たな街に到着した。")
    assert len(suggestions_filled) >= 1
    assert "主人公は新たな街に到着した。" in suggestions_filled[0]


def test_process_chapter_exact_max():
    """CHAPTER_MAX_LENGTH 文字の場合、そのまま返る。"""
    result = process_chapter("あ" * CHAPTER_MAX_LENGTH)
    assert result == "あ" * CHAPTER_MAX_LENGTH
