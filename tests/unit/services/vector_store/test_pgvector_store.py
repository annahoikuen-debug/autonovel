"""Unit tests for src/services/vector_store/pgvector.py with a fake async session."""
from unittest.mock import MagicMock

import pytest

import src.services.vector_store.pgvector as pg
from src.services.vector_store.pgvector import PgVectorStore, _embedding_to_pgvector


class FakeResult:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar = scalar_value

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class FakeSession:
    """SQL文字列の断片で応答を切り替えるフェイクセッション。

    ``responses`` は ``{sqlの断片: FakeResult}``。一致するものが無ければ空結果。
    """

    def __init__(self, responses=None, fail_on=None):
        self.executed = []
        self.committed = 0
        self.rolled_back = 0
        self._responses = dict(responses or {})
        self._fail_on = fail_on

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append((sql, params))
        if self._fail_on and self._fail_on in sql:
            raise RuntimeError(f"db error on {self._fail_on}")
        for fragment, result in self._responses.items():
            if fragment in sql:
                return result
        return FakeResult()

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self, *a, **k):
        return self.session


class FakeEngine:
    def __init__(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        self.disposed = 0

    async def dispose(self):
        self.disposed += 1


def make_store(session=None, **kwargs):
    """PgVectorStore を実際のDB接続なしで生成する。"""
    session = session if session is not None else FakeSession()
    engines = []

    def _engine(url, **kw):
        e = FakeEngine(url, **kw)
        engines.append(e)
        return e

    orig_engine = pg.create_async_engine
    orig_factory = pg.async_sessionmaker
    pg.create_async_engine = _engine
    pg.async_sessionmaker = lambda **kw: FakeSessionFactory(session)
    try:
        store = PgVectorStore("postgresql://u:p@localhost/db", **kwargs)
    finally:
        pg.create_async_engine = orig_engine
        pg.async_sessionmaker = orig_factory
    store.session = session
    store.engines = engines
    return store


class TestEmbeddingFormat:
    def test_format(self):
        assert _embedding_to_pgvector([1.0, 2.5]) == "[1.0, 2.5]"

    def test_empty(self):
        assert _embedding_to_pgvector([]) == "[]"

    def test_integers(self):
        assert _embedding_to_pgvector([1, 2]) == "[1, 2]"


class TestInit:
    def test_url_rewritten_to_asyncpg(self):
        store = make_store()
        assert store.engines[0].url.startswith("postgresql+asyncpg://")

    def test_engine_kwargs(self):
        store = make_store(pool_size=3, max_overflow=7, dimension=512)
        assert store.engines[0].kwargs["pool_size"] == 3
        assert store.engines[0].kwargs["max_overflow"] == 7
        assert store.dimension == 512

    def test_defaults(self):
        store = make_store()
        assert store.dimension == 1536
        assert store._initialized_tables == set()

    def test_raises_without_pgvector(self, monkeypatch):
        monkeypatch.setattr(pg, "HAS_PGVECTOR", False)
        with pytest.raises(RuntimeError, match="pgvector is not installed"):
            PgVectorStore("postgresql://x")

    async def test_get_session(self):
        store = make_store()
        s = await store._get_session()
        assert s is store.session

    async def test_session_context(self):
        store = make_store()
        async with store._session() as s:
            assert s is store.session


class TestValidation:
    @pytest.mark.parametrize("key", ["a", "A_1", "_", "a" * 64])
    def test_valid_keys(self, key):
        assert PgVectorStore._validate_metadata_key(key) == key

    @pytest.mark.parametrize("key", ["", "a" * 65, "a-b", "a b", "a;b", "日本語"])
    def test_invalid_keys(self, key):
        with pytest.raises(ValueError, match="Invalid metadata key"):
            PgVectorStore._validate_metadata_key(key)

    def test_table_name_sanitized(self):
        store = make_store()
        assert store._get_table_name("my-collection!") == "vec_my_collection"

    def test_table_name_truncated(self):
        store = make_store()
        name = store._get_table_name("a" * 100)
        assert name == "vec_" + "a" * 48

    def test_table_name_empty_becomes_default(self):
        store = make_store()
        assert store._get_table_name("!!!") == "vec_default"

    def test_table_name_passthrough(self):
        store = make_store()
        assert store._get_table_name("semantic_cache") == "vec_semantic_cache"


class TestEnsureTable:
    async def test_creates_table_and_indexes(self):
        session = FakeSession()
        store = make_store(session)
        assert await store._ensure_table("c") is True
        sqls = " | ".join(s for s, _ in session.executed)
        assert "CREATE EXTENSION IF NOT EXISTS vector" in sqls
        assert "CREATE TABLE IF NOT EXISTS vec_c" in sqls
        assert "USING hnsw" in sqls
        assert "USING gin" in sqls
        assert session.committed == 1
        assert "c" in store._initialized_tables

    async def test_cached_after_first_call(self):
        session = FakeSession()
        store = make_store(session)
        await store._ensure_table("c")
        n = len(session.executed)
        assert await store._ensure_table("c") is True
        assert len(session.executed) == n

    async def test_failure_rolls_back(self):
        session = FakeSession(fail_on="CREATE TABLE")
        store = make_store(session)
        assert await store._ensure_table("c") is False
        assert session.rolled_back == 1
        assert "c" not in store._initialized_tables

    async def test_failure_on_extension(self):
        session = FakeSession(fail_on="CREATE EXTENSION")
        store = make_store(session)
        assert await store._ensure_table("c") is False


class TestAddDocuments:
    async def test_add(self):
        session = FakeSession()
        store = make_store(session)
        await store.add_documents("c", ["a", "b"], ["d1", "d2"], [[1.0], [2.0]])
        sql, params = session.executed[-1]
        assert "INSERT INTO vec_c" in sql
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert params["doc0_id"] == "a"
        assert params["doc0_emb"] == "[1.0]"
        assert params["doc1_content"] == "d2"
        # FakeSessionFactory は常に同一セッションを返すため、
        # _ensure_table の DDL コミット + INSERT のコミット = 2 回になる。
        # 実 PG では _ensure_table は別セッションでコミットしている。
        assert session.committed == 2

    async def test_add_with_metadatas(self):
        session = FakeSession()
        store = make_store(session)
        await store.add_documents("c", ["a"], ["d"], [[1.0]], [{"g": 1}])
        _, params = session.executed[-1]
        assert params["doc0_meta"] == '{"g": 1}'

    async def test_add_without_metadatas(self):
        session = FakeSession()
        store = make_store(session)
        await store.add_documents("c", ["a"], ["d"], [[1.0]])
        _, params = session.executed[-1]
        assert params["doc0_meta"] == "{}"

    async def test_add_no_ids(self):
        session = FakeSession()
        store = make_store(session)
        await store.add_documents("c", [], [], [])
        assert session.executed == []

    async def test_add_batches(self):
        session = FakeSession()
        store = make_store(session)
        n = 250
        await store.add_documents("c", [f"i{i}" for i in range(n)], ["d"] * n, [[1.0]] * n)
        inserts = [s for s, _ in session.executed if "INSERT INTO" in s]
        assert len(inserts) == 3

    async def test_add_failure_raises(self):
        session = FakeSession(fail_on="INSERT INTO")
        store = make_store(session)
        with pytest.raises(RuntimeError):
            await store.add_documents("c", ["a"], ["d"], [[1.0]])
        assert session.rolled_back == 1


class TestSearch:
    def _rows(self):
        return FakeResult([("a", "content a", {"g": 1}, 0.1), ("b", "content b", None, 0.4)])

    async def test_search(self):
        session = FakeSession({"SELECT id, content, metadata, embedding": self._rows()})
        store = make_store(session)
        res = await store.search("c", [1.0, 0.0], top_k=2)
        assert [r["id"] for r in res] == ["a", "b"]
        assert res[0]["similarity"] == pytest.approx(0.9)
        assert res[0]["metadata"] == {"g": 1}
        assert res[1]["metadata"] == {}

    async def test_search_object_rows(self):
        row = MagicMock()
        row.id = "z"
        row.content = "cz"
        row.metadata = {"m": 1}
        row.distance = 0.25
        session = FakeSession({"SELECT id, content, metadata, embedding": FakeResult([row])})
        store = make_store(session)
        res = await store.search("c", [1.0])
        assert res[0]["id"] == "z"
        assert res[0]["similarity"] == pytest.approx(0.75)

    async def test_search_with_where(self):
        session = FakeSession({"SELECT id, content, metadata, embedding": self._rows()})
        store = make_store(session)
        await store.search("c", [1.0], where={"g": 1, "b": 2})
        sql, params = session.executed[-1]
        assert "WHERE metadata->>'g' = :meta_0" in sql
        assert params["meta_0"] == "1"
        assert params["meta_1"] == "2"
        assert params["limit"] == 5

    async def test_search_no_where(self):
        session = FakeSession({"SELECT id, content, metadata, embedding": self._rows()})
        store = make_store(session)
        await store.search("c", [1.0])
        sql, _ = session.executed[-1]
        assert "WHERE metadata" not in sql

    async def test_search_null_distance(self):
        session = FakeSession({"SELECT id, content, metadata, embedding": FakeResult([("a", "c", {}, None)])})
        store = make_store(session)
        res = await store.search("c", [1.0])
        assert res[0]["distance"] == 1.0
        assert res[0]["similarity"] == 0.0

    async def test_search_error_returns_empty(self):
        session = FakeSession(fail_on="SELECT id, content, metadata, embedding")
        store = make_store(session)
        assert await store.search("c", [1.0]) == []

    async def test_search_with_where_invalid_key(self):
        """不正な metadata key は fail-soft: 例外を投げず空リストを返す。"""
        session = FakeSession()
        store = make_store(session)
        assert await store.search("c", [1.0], where={"bad-key": 1}) == []

    async def test_search_with_score(self):
        session = FakeSession({"SELECT id, content, metadata, embedding": self._rows()})
        store = make_store(session)
        res = await store.search_with_score("c", [1.0], top_k=5)
        assert [r["id"] for r in res] == ["a", "b"]

    async def test_search_with_score_min_score(self):
        session = FakeSession({"SELECT id, content, metadata, embedding": self._rows()})
        store = make_store(session)
        res = await store.search_with_score("c", [1.0], min_score=0.8)
        assert [r["id"] for r in res] == ["a"]


class TestDeleteAndClear:
    async def test_delete(self):
        session = FakeSession()
        store = make_store(session)
        await store.delete_by_id("c", ["a", "b"])
        sql, params = session.executed[-1]
        assert "DELETE FROM vec_c" in sql
        assert params == {"id_0": "a", "id_1": "b"}
        assert session.committed == 1

    async def test_delete_no_ids(self):
        session = FakeSession()
        store = make_store(session)
        await store.delete_by_id("c", [])
        assert session.executed == []

    async def test_delete_failure(self):
        session = FakeSession(fail_on="DELETE")
        store = make_store(session)
        with pytest.raises(RuntimeError):
            await store.delete_by_id("c", ["a"])
        assert session.rolled_back == 1

    async def test_clear(self):
        session = FakeSession()
        store = make_store(session)
        await store.clear_collection("c")
        sql, _ = session.executed[-1]
        assert "TRUNCATE TABLE vec_c" in sql
        assert session.committed == 1

    async def test_clear_failure(self):
        session = FakeSession(fail_on="TRUNCATE")
        store = make_store(session)
        with pytest.raises(RuntimeError):
            await store.clear_collection("c")
        assert session.rolled_back == 1


class TestStats:
    async def test_stats(self):
        session = FakeSession({"SELECT COUNT": FakeResult(scalar_value=12)})
        store = make_store(session)
        res = await store.get_collection_stats("c")
        assert res == {"count": 12, "name": "c", "table": "vec_c"}

    async def test_stats_zero(self):
        session = FakeSession({"SELECT COUNT": FakeResult(scalar_value=None)})
        store = make_store(session)
        assert (await store.get_collection_stats("c"))["count"] == 0

    async def test_stats_error(self):
        session = FakeSession(fail_on="SELECT COUNT")
        store = make_store(session)
        res = await store.get_collection_stats("c")
        assert res["count"] == 0
        assert "error" in res


class TestFuseResults:
    def test_rrf_ordering(self):
        store = make_store()
        vector = [
            {"id": "a", "content": "ca", "metadata": {"g": 1}, "similarity": 0.9},
            {"id": "b", "content": "cb", "metadata": {}, "similarity": 0.5},
        ]
        text = [{"id": "b", "content": "cb", "metadata": {"g": 2}, "rank": 0.8}]
        res = store._fuse_results(vector, text, top_k=5, alpha=0.5, min_score=0.0)
        ids = [r["id"] for r in res]
        assert set(ids) == {"a", "b"}
        assert ids[0] == "a"
        assert res[0]["metadata"] == {"g": 1}

    def test_metadata_fallback_to_text(self):
        store = make_store()
        vector = [{"id": "b", "content": "cb", "metadata": {}, "similarity": 0.5}]
        text = [{"id": "b", "content": "cb", "metadata": {"g": 2}, "rank": 0.8}]
        res = store._fuse_results(vector, text, top_k=5, alpha=0.5, min_score=0.0)
        assert res[0]["metadata"] == {"g": 2}
        assert res[0]["text_rank"] == 0.8

    def test_min_score_filters(self):
        store = make_store()
        vector = [{"id": "a", "content": "c", "metadata": {}, "similarity": 1.0}]
        assert store._fuse_results(vector, [], 5, 0.5, 99.0) == []

    def test_top_k_limit(self):
        store = make_store()
        vector = [
            {"id": "a", "content": "c", "metadata": {}, "similarity": 1.0},
            {"id": "b", "content": "c", "metadata": {}, "similarity": 0.9},
        ]
        assert len(store._fuse_results(vector, [], 1, 0.5, 0.0)) == 1

    def test_empty_inputs(self):
        store = make_store()
        assert store._fuse_results([], [], 5, 0.5, 0.0) == []


class TestHybridSearch:
    async def test_hybrid(self):
        session = FakeSession(
            {
                "SELECT id, content, metadata, embedding": FakeResult([("a", "ca", {"g": 1}, 0.1)]),
                "ts_rank_cd": FakeResult([("b", "cb", {"g": 2}, 0.8)]),
            }
        )
        store = make_store(session)
        res = await store.hybrid_search("c", "query", [1.0], top_k=5)
        assert {r["id"] for r in res} == {"a", "b"}
        assert "rrf_score" in res[0]

    async def test_hybrid_with_where(self):
        session = FakeSession(
            {
                "SELECT id, content, metadata, embedding": FakeResult([]),
                "ts_rank_cd": FakeResult([]),
            }
        )
        store = make_store(session)
        await store.hybrid_search("c", "query", [1.0], where={"g": 1})
        sql, params = session.executed[-1]
        assert "AND metadata->>'g' = :meta_0" in sql
        assert params["meta_0"] == "1"
        assert params["limit"] == 15

    async def test_hybrid_alpha_clamped(self):
        session = FakeSession(
            {
                "SELECT id, content, metadata, embedding": FakeResult([]),
                "ts_rank_cd": FakeResult([]),
            }
        )
        store = make_store(session)
        assert await store.hybrid_search("c", "q", [1.0], alpha=-3.0) is not None
        assert await store.hybrid_search("c", "q", [1.0], alpha=9.0) is not None

    async def test_hybrid_fulltext_error_swallowed(self):
        session = FakeSession(fail_on="ts_rank_cd")
        store = make_store(session)
        res = await store.hybrid_search("c", "q", [1.0])
        assert res == []

    async def test_hybrid_object_rows(self):
        row = MagicMock()
        row.id = "t"
        row.content = "ct"
        row.metadata = None
        row.rank = None
        session = FakeSession({"ts_rank_cd": FakeResult([row])})
        store = make_store(session)
        res = await store.hybrid_search("c", "q", [1.0])
        assert res[0]["id"] == "t"
        assert res[0]["text_rank"] == 0.0

    async def test_hybrid_tuple_rows(self):
        session = FakeSession(
            {
                "SELECT id, content, metadata, embedding": FakeResult([]),
                "ts_rank_cd": FakeResult([("t", "ct", {"m": 1}, 0.4)]),
            }
        )
        store = make_store(session)
        res = await store.hybrid_search("c", "q", [1.0])
        assert res[0]["metadata"] == {"m": 1}

    async def test_hybrid_invalid_where_key(self):
        """不正な metadata key は fail-soft: 例外を投げず空リストを返す。"""
        session = FakeSession()
        store = make_store(session)
        assert await store.hybrid_search("c", "q", [1.0], where={"bad key": 1}) == []


class TestClose:
    async def test_close(self):
        store = make_store()
        await store.close()
        assert store.engines[0].disposed == 1


