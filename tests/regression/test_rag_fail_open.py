"""T9: RAG パイプライン fail-open 回帰テスト (Plan R5 C6 / T9).

検索 / 整形 / リランク のいずれかで例外が発生しても、執筆が止まらず
``rag_context=[]`` に倒れる（現行仕様の固定）。これが壊れると CI 落ち。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.integrations.rag.reflective_rag import ReflectiveRAGService


def test_hybrid_retriever_exception_is_swallowed() -> None:
    """hybrid_retriever.search が例外を投げても retrieve_with_reflection は継続する。"""
    hybrid = MagicMock()
    hybrid.search.side_effect = RuntimeError("BM25 index broken")

    rag_service = MagicMock()
    rag_service.search_similar_chunks.return_value = []

    rag = ReflectiveRAGService(
        rag_service=rag_service,
        hybrid_retriever=hybrid,
        top_k=2,
        max_iter=1,
        relevance_threshold=0.5,
    )

    session = MagicMock()
    result = None
    try:
        import asyncio

        result = asyncio.run(
            rag.retrieve_with_reflection(session=session, query="q", book_id=1)
        )
    except Exception as e:
        raise AssertionError(f"fail-open 違反: 例外が外部に漏れた {e!r}")

    # 例外を握り潰して処理継続し、documents は空（または dense 結果）になる
    assert result is not None
    assert isinstance(result.documents, list)
