import pytest
from unittest.mock import AsyncMock, patch

from src.services.digest_service import generate_suggestions, process_chapter


def test_process_chapter():
    """process_chapter の文字数トリムと省略記号付与の検証。"""
    short_text = "短い章本文です。"
    assert process_chapter(short_text) == short_text

    long_text = "あ" * 2000
    processed = process_chapter(long_text)
    assert len(processed) <= 1505
    assert processed.endswith("...")


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
