"""T5: EpisodeBM25Index 単体テスト (Plan R5 C6 / T5).

日本語固有名詞の拾い上げ・LRU キャッシュ・RAG_BM25_MAX_DOCS 超過で dense フォールバック（None）・
空コーパスを検証。DB は MagicMock でモック（LLM・外部 DB 不使用）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.integrations.rag.bm25_index import EpisodeBM25Index


def _mk_session(chunks):
    session = MagicMock()
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = chunks
    session.query.return_value = query
    return session


def _mk_chunk(cid: str, content: str):
    chunk = MagicMock()
    chunk.id = cid
    chunk.content = content
    chunk.chunk_metadata = {"type": "lore", "book_id": 1}
    return chunk


def test_build_and_search_wires_query_to_bm25(monkeypatch) -> None:
    # BM25Okapi は極小コーパスで IDF が負になり score<=0 の文書を採用しない
    # (ライブラリ仕様)。配線を検証するため get_scores を差し替える。
    chunks = [_mk_chunk("1", "古代魔法アルカディアは王都で使われた。")]
    session = _mk_session(chunks)
    idx = EpisodeBM25Index(max_docs=1000)
    retriever = idx.get(session, book_id=1)
    assert retriever is not None

    called = {}
    orig_get_scores = retriever._bm25.get_scores

    def fake_get_scores(query_tokens):
        called["tokens"] = query_tokens
        return [1.0]

    monkeypatch.setattr(retriever._bm25, "get_scores", fake_get_scores)
    res = idx.search(session, book_id=1, query="アルカディア", top_k=5)
    assert len(res) == 1
    assert res[0].id == "1"
    assert called["tokens"] == ["アルカディア"]


def test_max_docs_exceeds_returns_none_dense_fallback() -> None:
    chunks = [_mk_chunk(str(i), f"content {i}") for i in range(6000)]
    session = _mk_session(chunks)
    idx = EpisodeBM25Index(max_docs=100)
    assert idx.get(session, book_id=1) is None, "max_docs 超過で None (dense フォールバック)"


def test_empty_corpus_returns_none() -> None:
    session = _mk_session([])
    idx = EpisodeBM25Index()
    assert idx.get(session, book_id=1) is None


def test_lru_cache_reuse() -> None:
    chunks = [_mk_chunk("1", "アルカディア魔法")]
    session = _mk_session(chunks)
    idx = EpisodeBM25Index(max_docs=1000)
    r1 = idx.get(session, book_id=1)
    r2 = idx.get(session, book_id=1)
    assert r1 is r2, "同じ book_id ならキャッシュから再利用"


def test_search_when_index_none_returns_empty() -> None:
    chunks = [_mk_chunk(str(i), f"content {i}") for i in range(6000)]
    session = _mk_session(chunks)
    idx = EpisodeBM25Index(max_docs=100)
    assert idx.search(session, book_id=1, query="q", top_k=5) == []


def test_session_exception_returns_none_fail_open() -> None:
    session = MagicMock()
    session.query.side_effect = RuntimeError("DB down")
    idx = EpisodeBM25Index(max_docs=1000)
    assert idx.get(session, book_id=1) is None, "DB 例外でも None (fail-open)"
