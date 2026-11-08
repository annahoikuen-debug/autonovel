"""ReflectiveRAGService が例外を握り潰して空を返さず、正常に文書を返すことを検証.

src/integrations/rag/reflective_rag.py:644-651 の安全フォールバックにより、
予期せぬ例外時でも `initial_candidates` が空なら `[]` を返す。
LLM 未設定（rag_service.age_client=None）でも、search_similar_chunks が正常に
動作すれば documents が空にならないことを検証する。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.rag.rag_service import GraphRAGService, SearchResult
from src.services.reflective_rag import ReflectiveRAGService


@pytest.fixture
def sample_search_results():
    return [
        SearchResult(
            id="doc-1",
            content="古代魔法アルカディアは王都で使われた。",
            metadata={"entity_name": "アルカディア", "is_forbidden": False},
            source="vector",
            score=0.95,
        ),
        SearchResult(
            id="doc-2",
            content="禁忌魔法カオス・ヴォイドは世界の理を乱す。",
            metadata={"entity_name": "カオス・ヴォイド", "is_forbidden": True},
            source="vector",
            score=0.92,
        ),
    ]


@pytest.mark.asyncio
async def test_retrieve_with_reflection_returns_docs(sample_search_results) -> None:
    """LLM 未設定（age_client=None）でも、search_similar_chunks が正常に動作すれば
    documents が空にならないこと（例外を握り潰して空を返さない）."""
    mock_rag = MagicMock(spec=GraphRAGService)
    mock_rag.search_similar_chunks = AsyncMock(return_value=sample_search_results)
    mock_rag.age_client = None

    rag = ReflectiveRAGService(
        rag_service=mock_rag,
        top_k=2,
        max_iter=2,
        relevance_threshold=0.5,
    )

    session = MagicMock()
    result = await rag.retrieve_with_reflection(
        session=session,
        query="テストクエリ",
        book_id=1,
    )

    assert len(result.documents) > 0, f"documents が空: {result.documents}"
    # 各ドキュメントに内容が含まれていること。
    # ReflectiveDoc は search_result: SearchResult を保持し、SearchResult.content が実体。
    # （以前は `str(first)` へのフォールバックがあり、中身が空でも str() が真となり検知力がゼロだった）
    first = result.documents[0]
    assert first.search_result.content, f"最初のドキュメントの内容が空: {first}"


@pytest.mark.asyncio
async def test_retrieve_with_reflection_search_exception_does_not_crash(sample_search_results) -> None:
    """search_similar_chunks が例外を投げても、retrieve_with_reflection がクラッシュしないこと
    （例外を握り潰してフォールバック結果を返すこと）."""
    mock_rag = MagicMock(spec=GraphRAGService)
    mock_rag.search_similar_chunks = AsyncMock(side_effect=Exception("DB connection failed"))
    mock_rag.age_client = None

    rag = ReflectiveRAGService(
        rag_service=mock_rag,
        top_k=2,
        max_iter=2,
        relevance_threshold=0.5,
    )

    session = MagicMock()
    result = await rag.retrieve_with_reflection(
        session=session,
        query="テストクエリ",
        book_id=1,
    )

    # 例外が握り潰され、result は返される（documents は [] の可能性もあるが、クラッシュしない）
    assert result is not None
