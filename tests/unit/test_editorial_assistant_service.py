"""EditorialAssistantService 回帰テスト。

ask_bible の rag.search_similar_chunks が list[SearchResult] を返す場合に、
"\n---\n".join(...) で TypeError にならないことを検証する。
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.rag.rag_service import SearchResult
from src.models.editor import AskBibleRequest
from src.services.editorial_assistant_service import EditorialAssistantService


@dataclass
class _FakeSession:
    pass


@pytest.mark.asyncio
async def test_ask_bible_with_search_results():
    """rag.search_similar_chunks が SearchResult リストを返しても ask_bible が例外なく回答を返すこと。"""
    chunks = [
        SearchResult(
            id="chunk_1",
            content="過去章の抜粋A",
            metadata={},
            source="vector",
            score=0.9,
        ),
        SearchResult(
            id="chunk_2",
            content="過去章の抜粋B",
            metadata={},
            source="vector",
            score=0.8,
        ),
    ]

    mock_rag = MagicMock()
    mock_rag.search_similar_chunks = AsyncMock(return_value=chunks)
    mock_rag.get_graph_context = MagicMock(return_value=[])
    mock_rag.rerank_graph_neighbors = AsyncMock(return_value=[])

    class _FakeLLMResult:
        story_content = "AIからの回答です"

    mock_llm = MagicMock()
    mock_llm.generate_text = AsyncMock(return_value=_FakeLLMResult())

    service = EditorialAssistantService(rag_service=mock_rag, llm_gateway=mock_llm)

    session = _FakeSession()
    request = AskBibleRequest(book_id=1, query="テストクエリ")

    response = await service.ask_bible(session, request)

    # TypeError なく回答が返ること（join(SearchResult) が修正されていることの証左）
    assert response is not None
    assert response.answer == "AIからの回答です"

    # generate_text に渡されたプロンプトに過去章の抜粋が含まれていること
    call_kwargs = mock_llm.generate_text.call_args.kwargs
    prompt = call_kwargs["prompt"]
    assert "過去章の抜粋A" in prompt
    assert "過去章の抜粋B" in prompt
