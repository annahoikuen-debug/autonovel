"""T4: HybridRetriever 単体テスト (Plan R5 C6 / T4).

RRF 融合順序・max 正規化・metadata（rrf_raw_score/dense_rank/sparse_rank）・
片側空リスト・重複 id を検証する。LLM・DB 不使用。
"""

from __future__ import annotations

from src.integrations.rag.hybrid_retriever import HybridRetriever
from src.integrations.rag.rag_service import SearchResult


def _mk_result(cid: str, source: str, score: float) -> SearchResult:
    return SearchResult(id=cid, content=cid, source=source, score=score, metadata={})


class _FakeRetriever:
    def __init__(self, results) -> None:
        self.results = results

    def search(self, query: str, top_k: int = 5, fetch_k: int = 20):
        return self.results[:top_k]

    def search_async(self, query: str, top_k: int = 5, fetch_k: int = 20):
        return self.results[:top_k]


def test_fuse_orders_both_sides_by_rrf() -> None:
    # "b" は両リストに現れる → RRF で最高スコアになるはず
    dense = [_mk_result("a", "vector", 0.9), _mk_result("b", "vector", 0.8)]
    sparse = [_mk_result("b", "bm25", 5.0), _mk_result("c", "bm25", 4.0)]
    hr = HybridRetriever(
        dense_retriever=_FakeRetriever(dense),
        sparse_retriever=_FakeRetriever(sparse),
        default_rrf_k=60,
        dense_weight=1.0,
        sparse_weight=1.0,
    )
    res = hr.search("q", top_k=5)
    ids = [r.id for r in res]
    assert ids[0] == "b", f"両リストに現れる文書が最上位に来るべき: {ids}"
    assert res[0].metadata["dense_rank"] == 2
    assert res[0].metadata["sparse_rank"] == 1
    assert res[0].metadata["rrf_raw_score"] is not None
    assert res[0].source == "hybrid_rrf"
    # 正規化: 最高スコアが 1.0
    assert abs(res[0].score - 1.0) < 1e-9


def test_sparse_only_when_dense_empty() -> None:
    sparse = [_mk_result("x", "bm25", 3.0)]
    hr = HybridRetriever(
        dense_retriever=_FakeRetriever([]),
        sparse_retriever=_FakeRetriever(sparse),
    )
    res = hr.search("q", top_k=5)
    assert [r.id for r in res] == ["x"]


def test_dense_only_when_sparse_empty() -> None:
    dense = [_mk_result("y", "vector", 0.7)]
    hr = HybridRetriever(
        dense_retriever=_FakeRetriever(dense),
        sparse_retriever=_FakeRetriever([]),
    )
    res = hr.search("q", top_k=5)
    assert [r.id for r in res] == ["y"]


def test_both_empty_returns_empty() -> None:
    hr = HybridRetriever(
        dense_retriever=_FakeRetriever([]),
        sparse_retriever=_FakeRetriever([]),
    )
    assert hr.search("q", top_k=5) == []


def test_top_k_limits_output() -> None:
    dense = [_mk_result(f"d{i}", "vector", 0.9 - i * 0.01) for i in range(20)]
    sparse = [_mk_result(f"s{i}", "bm25", 5.0 - i * 0.1) for i in range(20)]
    hr = HybridRetriever(
        dense_retriever=_FakeRetriever(dense),
        sparse_retriever=_FakeRetriever(sparse),
    )
    res = hr.search("q", top_k=3)
    assert len(res) == 3
