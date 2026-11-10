"""T7: HyDE 単体テスト (Plan R5 D1-D2 / T7).

LLM ベースの擬似文書生成・フォールバック・2-クエリ RRF を検証。
LLM はモックを使用し、実際の API 呼び出しは行わない。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.rag.query_reformulator import QueryReformulator


class _AsyncLLM:
    def __init__(self, text: str | None = None, exc: Exception | None = None) -> None:
        self.text = text
        self.exc = exc
        self.calls = 0

    async def generate(self, prompt: str) -> str:
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.text or ""


def test_hyde_template_fallback_when_no_llm() -> None:
    qr = QueryReformulator(llm_adapter=None)
    import asyncio

    out = asyncio.run(qr.generate_hypothetical_chunk_async("古代魔法", timeout_seconds=0.5))
    assert "古代魔法" in out
    assert "世界観アーカイブ" in out


def test_hyde_llm_mode_returns_llm_output() -> None:
    llm = _AsyncLLM(text="【擬似文書】古代魔法アルカディアは王都の禁忌である。")
    qr = QueryReformulator(llm_adapter=llm)
    import asyncio

    out = asyncio.run(qr.generate_hypothetical_chunk_async("古代魔法", timeout_seconds=0.5))
    assert out == "【擬似文書】古代魔法アルカディアは王都の禁忌である。"
    assert llm.calls == 1


def test_hyde_llm_timeout_falls_back_to_template() -> None:
    llm = _AsyncLLM(exc=TimeoutError())
    qr = QueryReformulator(llm_adapter=llm)
    import asyncio

    out = asyncio.run(qr.generate_hypothetical_chunk_async("古代魔法", timeout_seconds=0.01))
    assert "古代魔法" in out  # テンプレートフォールバック


def test_query_composer_keywords_feed_hyde() -> None:
    from src.integrations.rag.query_composer import QueryComposer

    qc = QueryComposer()
    r = qc.compose_episode_query(
        plot_summary="アルカディアの古代魔法",
        foreshadowing_keywords=["禁忌魔法"],
    )
    assert "禁忌魔法" in r["keywords"]
    assert len(r["keywords"]) <= 8


def test_reflective_rag_hyde_calls_search_twice(monkeypatch) -> None:
    """HyDE モードでは元クエリと擬似文書の両方で dense 検索し、マージする。"""
    import src.integrations.rag.reflective_rag as rr_mod
    from src.integrations.rag.rag_service import SearchResult

    monkeypatch.setattr(rr_mod.settings, "RAG_HYDE_MODE", "llm")

    call_queries = []

    def fake_search(session, *, query, limit, min_score):
        call_queries.append(query)
        if "元クエリ" in query:
            return [SearchResult(id="doc-1", content="元クエリ結果", source="vector", score=0.9, metadata={})]
        return [SearchResult(id="doc-2", content="擬似文書結果", source="vector", score=0.8, metadata={})]

    rag_service = MagicMock()
    rag_service.search_similar_chunks.side_effect = fake_search

    llm = _AsyncLLM(text="【擬似文書】古代魔法アルカディアに関する記述。")
    qr = QueryReformulator(llm_adapter=llm)

    rag = rr_mod.ReflectiveRAGService(
        rag_service=rag_service,
        hybrid_retriever=None,
        query_reformulator=qr,
        top_k=2,
        max_iter=1,
        relevance_threshold=0.0,
    )

    session = MagicMock()
    import asyncio

    result = asyncio.run(rag.retrieve_with_reflection(session=session, query="元クエリ", book_id=1))
    assert call_queries == ["元クエリ", "【擬似文書】古代魔法アルカディアに関する記述。"]
    ids = {getattr(getattr(d, "search_result", d), "id", None) for d in result.documents}
    assert ids == {"doc-1", "doc-2"}
