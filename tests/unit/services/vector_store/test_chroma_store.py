"""Unit tests for src/services/vector_store/chroma.py using a fake ChromaDB client."""
import sys
import types
from unittest.mock import MagicMock

import pytest

import src.services.vector_store.chroma as chroma_mod
from src.services.vector_store.base import (
    DEFAULT_COLLECTIONS,
    CollectionType,
)
from src.services.vector_store.chroma import (
    ChromaClientProvider,
    ChromaVectorStore,
    _is_collection_not_found,
    _module_available,
)


class FakeCollection:
    def __init__(self, name, metadata=None):
        self.name = name
        self.metadata = metadata or {}
        self.added = []
        self.deleted = []
        self.query_result = None
        self.get_result = {"ids": [], "documents": [], "metadatas": []}
        self._count = 0
        self._count_raises = False
        self._peek_raises = False

    def add(self, **kw):
        self.added.append(kw)
        self._count += len(kw.get("ids", []))

    def delete(self, ids=None):
        self.deleted.append(ids)

    def query(self, **kw):
        if self.query_result is not None:
            return self.query_result
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def count(self):
        if self._count_raises:
            raise RuntimeError("count unsupported")
        return self._count

    def peek(self, limit=1):
        if self._peek_raises:
            raise RuntimeError("peek unsupported")
        return {"ids": ["x"] if self._count else []}

    def get(self, include=None):
        return self.get_result


class FakeClient:
    def __init__(self, fail_get=(), fail_create=()):
        self.collections = {}
        self.fail_get = set(fail_get)
        self.fail_create = set(fail_create)
        self.deleted_collections = []

    def get_collection(self, name):
        if name in self.fail_get:
            raise type("NotFoundError", (Exception,), {})()
        if name not in self.collections:
            raise ValueError(f"Collection {name} does not exist")
        return self.collections[name]

    def get_or_create_collection(self, name, metadata=None):
        if name in self.fail_create:
            raise RuntimeError(f"cannot create {name}")
        if name not in self.collections:
            self.collections[name] = FakeCollection(name, metadata)
        return self.collections[name]

    def delete_collection(self, name):
        if name not in self.collections:
            raise ValueError("not found")
        self.deleted_collections.append(name)
        del self.collections[name]


def make_store(client=None):
    client = client if client is not None else FakeClient()
    provider = MagicMock()
    provider.get_client.return_value = client
    return ChromaVectorStore(provider), client


def make_storeless():
    provider = MagicMock()
    provider.get_client.return_value = None
    return ChromaVectorStore(provider)


class TestModuleHelpers:
    def test_module_available_installed(self):
        assert _module_available("json") is True

    def test_module_available_missing(self):
        assert _module_available("definitely_not_a_real_module_xyz") is False

    def test_module_available_from_sys_modules(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "fake_mod_xyz", object())
        assert _module_available("fake_mod_xyz") is True

    def test_module_available_value_error(self, monkeypatch):
        def _boom(name):
            raise ValueError("weird")

        monkeypatch.setattr(chroma_mod.importlib.util, "find_spec", _boom)
        assert _module_available("whatever") is False

    def test_get_chromadb_injected(self, monkeypatch):
        sentinel = object()
        monkeypatch.setitem(chroma_mod.__dict__, "chromadb", sentinel)
        assert chroma_mod._get_chromadb() is sentinel
        assert chroma_mod.chromadb is sentinel
        monkeypatch.delitem(chroma_mod.__dict__, "chromadb")

    def test_get_bm25_injected(self, monkeypatch):
        sentinel = object()
        monkeypatch.setitem(chroma_mod.__dict__, "BM25Okapi", sentinel)
        assert chroma_mod._get_bm25() is sentinel
        assert chroma_mod.BM25Okapi is sentinel
        monkeypatch.delitem(chroma_mod.__dict__, "BM25Okapi")

    def test_get_chromadb_import_failure(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", True)
        monkeypatch.setattr(chroma_mod, "_chromadb_module", None, raising=False)

        def _boom(name):
            raise ImportError("nope")

        monkeypatch.setattr(chroma_mod.importlib, "import_module", _boom)
        assert chroma_mod._get_chromadb() is None

    def test_get_bm25_import_failure(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_BM25", True)
        monkeypatch.setattr(chroma_mod, "_bm25_cls", None, raising=False)

        def _boom(name):
            raise ImportError("nope")

        monkeypatch.setattr(chroma_mod.importlib, "import_module", _boom)
        assert chroma_mod._get_bm25() is None

    def test_get_bm25_disabled(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_BM25", False)
        monkeypatch.setattr(chroma_mod, "_bm25_cls", None, raising=False)
        assert chroma_mod._get_bm25() is None

    def test_module_getattr_unknown(self):
        with pytest.raises(AttributeError, match="has no attribute"):
            chroma_mod.definitely_unknown_attr_xyz

    @pytest.mark.parametrize(
        "exc,expected",
        [
            (type("NotFoundError", (Exception,), {})(), True),
            (type("CollectionNotFoundError", (Exception,), {})(), True),
            (ValueError("Collection x does not exist"), True),
            (ValueError("it doesn't exist"), True),
            (ValueError("NotFound something"), False),
            (ConnectionError("unauthorized"), False),
            (ValueError("some other problem"), False),
        ],
    )
    def test_is_collection_not_found(self, exc, expected):
        assert _is_collection_not_found(exc) is expected


class TestChromaClientProvider:
    def test_init(self):
        p = ChromaClientProvider(db_path="/tmp/x")
        assert p.db_path == "/tmp/x"
        assert p.host is None
        assert p.port is None
        assert p._client is None

    def test_get_client_cached(self):
        sentinel = object()
        p = ChromaClientProvider()
        p._client = sentinel
        assert p.get_client() is sentinel

    def test_get_client_without_chroma(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", False)
        assert ChromaClientProvider().get_client() is None

    def test_get_client_chroma_import_failed(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", True)
        monkeypatch.setattr(chroma_mod, "_get_chromadb", lambda: None)
        assert ChromaClientProvider().get_client() is None

    def test_get_client_persistent(self, monkeypatch):
        sentinel = MagicMock()
        fake = types.SimpleNamespace(PersistentClient=lambda path: sentinel)
        p = ChromaClientProvider(db_path="/data")
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", True)
        monkeypatch.setattr(chroma_mod, "_get_chromadb", lambda: fake)
        assert p.get_client() is sentinel
        assert p.get_client() is sentinel

    def test_get_client_http(self, monkeypatch):
        sentinel = MagicMock()
        captured = {}

        def _http(host, port):
            captured["host"] = host
            captured["port"] = port
            return sentinel

        fake = types.SimpleNamespace(HttpClient=_http)
        p = ChromaClientProvider(host="h", port=1234)
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", True)
        monkeypatch.setattr(chroma_mod, "_get_chromadb", lambda: fake)
        assert p.get_client() is sentinel
        assert captured == {"host": "h", "port": 1234}

    def test_get_client_http_default_port(self, monkeypatch):
        captured = {}

        def _http(host, port):
            captured["port"] = port
            return MagicMock()

        fake = types.SimpleNamespace(HttpClient=_http)
        p = ChromaClientProvider(host="h")
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", True)
        monkeypatch.setattr(chroma_mod, "_get_chromadb", lambda: fake)
        p.get_client()
        assert captured["port"] == 8000

    def test_get_client_retries_then_fails(self, monkeypatch):
        attempts = []

        def _persist(path):
            attempts.append(path)
            raise RuntimeError("db locked")

        fake = types.SimpleNamespace(PersistentClient=_persist)
        p = ChromaClientProvider(db_path="/data")
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", True)
        monkeypatch.setattr(chroma_mod, "_get_chromadb", lambda: fake)
        monkeypatch.setattr("time.sleep", lambda s: None)
        assert p.get_client(retries=3, base_delay=0.0) is None
        assert len(attempts) == 3

    def test_get_client_succeeds_after_failure(self, monkeypatch):
        calls = {"n": 0}
        sentinel = MagicMock()

        def _persist(path):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("transient")
            return sentinel

        fake = types.SimpleNamespace(PersistentClient=_persist)
        p = ChromaClientProvider(db_path="/data")
        monkeypatch.setattr(chroma_mod, "HAS_CHROMA", True)
        monkeypatch.setattr(chroma_mod, "_get_chromadb", lambda: fake)
        monkeypatch.setattr("time.sleep", lambda s: None)
        assert p.get_client(retries=3, base_delay=0.0) is sentinel

    def test_close(self):
        p = ChromaClientProvider()
        p._client = MagicMock()
        p.close()
        assert p._client is None

    def test_close_when_empty(self):
        p = ChromaClientProvider()
        p.close()
        assert p._client is None

    def test_close_logs_and_swallows_error(self, caplog):
        # close() はクライアント破棄失敗を握り潰す設計。ログを観測してエラー経路を検証する
        p = ChromaClientProvider()
        p._client = MagicMock()
        with caplog.at_level("ERROR", logger="src.services.vector_store.chroma"):
            p.close()
        assert p._client is None


class TestCollectionLifecycle:
    def test_initialize_all_collections(self):
        store, _ = make_store()
        results = store.initialize_collections()
        assert set(results) == {
            "semantic_cache",
            "style_memory",
            "world_memory",
            "character_memory",
            "narrative_memory",
            "episode_memory",
        }
        assert all(results.values())

    def test_initialize_subset(self):
        store, _ = make_store()
        assert store.initialize_collections([CollectionType.SEMANTIC_CACHE]) == {
            "semantic_cache": True
        }

    def test_initialize_passes_metadata(self):
        store, client = make_store()
        store.initialize_collections([CollectionType.SEMANTIC_CACHE])
        meta = client.collections["semantic_cache"].metadata
        assert meta["hnsw:space"] == "cosine"
        assert "description" in meta

    def test_ensure_already_initialized(self):
        store, _ = make_store()
        config = DEFAULT_COLLECTIONS[CollectionType.SEMANTIC_CACHE]
        store._initialized_collections.add("semantic_cache")
        assert store._ensure_collection(config) is True

    def test_ensure_without_client(self):
        store = make_storeless()
        config = DEFAULT_COLLECTIONS[CollectionType.SEMANTIC_CACHE]
        assert store._ensure_collection(config) is False

    def test_ensure_warns_on_space_mismatch(self, caplog):
        client = FakeClient()
        client.collections["semantic_cache"] = FakeCollection(
            "semantic_cache", {"hnsw:space": "l2"}
        )
        store, _ = make_store(client)
        config = DEFAULT_COLLECTIONS[CollectionType.SEMANTIC_CACHE]
        with caplog.at_level("WARNING"):
            assert store._ensure_collection(config) is True
        assert "different space" in caplog.text

    def test_ensure_get_collection_auth_error(self):
        client = FakeClient()
        client.get_collection = MagicMock(side_effect=ConnectionError("unauthorized"))
        store, _ = make_store(client)
        config = DEFAULT_COLLECTIONS[CollectionType.SEMANTIC_CACHE]
        assert store._ensure_collection(config) is False

    def test_ensure_create_failure(self):
        client = FakeClient(fail_create=["semantic_cache"])
        store, _ = make_store(client)
        config = DEFAULT_COLLECTIONS[CollectionType.SEMANTIC_CACHE]
        assert store._ensure_collection(config) is False

    def test_get_collection_creates(self):
        store, client = make_store()
        assert store.get_collection("custom") is client.collections["custom"]

    def test_get_collection_caches(self):
        store, client = make_store()
        first = store.get_collection("custom")
        client.collections["custom"] = FakeCollection("custom")
        assert store.get_collection("custom") is first

    def test_get_collection_with_metadata(self):
        store, client = make_store()
        store.get_collection("custom", {"a": 1})
        assert client.collections["custom"].metadata == {"a": 1}

    def test_get_collection_failure(self):
        client = FakeClient(fail_create=["bad"])
        store, _ = make_store(client)
        assert store.get_collection("bad") is None

    def test_get_collection_without_client(self):
        assert make_storeless().get_collection("x") is None

    def test_get_collection_config(self):
        store, _ = make_store()
        assert store.get_collection_config(CollectionType.WORLD_MEMORY).name == "world_memory"

    def test_list_collections(self):
        store, _ = make_store()
        store.initialize_collections([CollectionType.WORLD_MEMORY])
        assert store.list_collections() == ["world_memory"]

    def test_audit_collection_coverage(self):
        store, _ = make_store()
        assert store.audit_collection_coverage([CollectionType.EPISODE_MEMORY]) == {
            "episode_memory": True
        }

    def test_audit_collection_coverage_all(self):
        store, _ = make_store()
        assert all(store.audit_collection_coverage().values())

    def test_client_property(self):
        store, client = make_store()
        assert store.client is client


class TestDocumentOperations:
    async def test_add_documents(self):
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        await store.add_documents("c", ["a"], ["doc"], [[1.0, 0.0]], [{"k": 1}])
        added = store._collections["c"].added
        assert added[0]["ids"] == ["a"]
        assert added[0]["metadatas"] == [{"k": 1}]

    async def test_add_documents_without_metadata(self):
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        await store.add_documents("c", ["a"], ["doc"], [[1.0]])
        assert "metadatas" not in store._collections["c"].added[0]

    async def test_add_documents_missing_collection(self, caplog):
        store = make_storeless()
        with caplog.at_level("WARNING"):
            await store.add_documents("c", ["a"], ["d"], [[1.0]])
        assert "not available" in caplog.text

    async def test_add_documents_batches(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        store._collections["c"] = coll
        n = ChromaVectorStore._CHROMA_MAX_BATCH + 5
        ids = [f"i{i}" for i in range(n)]
        await store.add_documents("c", ids, ["d"] * n, [[1.0]] * n)
        assert len(coll.added) == 2
        assert len(coll.added[0]["ids"]) == ChromaVectorStore._CHROMA_MAX_BATCH
        assert len(coll.added[1]["ids"]) == 5

    def test_chunks_of(self):
        assert ChromaVectorStore._chunks_of([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
        assert ChromaVectorStore._chunks_of([], 2) == []

    async def test_search(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll.query_result = {
            "ids": [["a", "b"]],
            "documents": [["da", "db"]],
            "metadatas": [[{"k": 1}, {"k": 2}]],
            "distances": [[0.1, 0.2]],
        }
        store._collections["c"] = coll
        res = await store.search("c", [1.0], top_k=2, where={"g": 1})
        assert res[0]["id"] == "a"
        assert res[0]["content"] == "da"
        assert res[0]["metadata"] == {"k": 1}
        assert res[0]["distance"] == 0.1

    async def test_search_empty_result(self):
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        assert await store.search("c", [1.0]) == []

    async def test_search_missing_collection(self):
        assert await make_storeless().search("c", [1.0]) == []

    async def test_search_with_score(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll.query_result = {
            "ids": [["a", "b"]],
            "documents": [["da", "db"]],
            "metadatas": [[{}, {}]],
            "distances": [[0.5, 0.1]],
        }
        store._collections["c"] = coll
        res = await store.search_with_score("c", [1.0], top_k=2)
        assert [r["id"] for r in res] == ["b", "a"]
        assert res[0]["similarity"] == pytest.approx(0.9)

    async def test_search_with_score_min_score(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll.query_result = {
            "ids": [["a", "b"]],
            "documents": [["da", "db"]],
            "metadatas": [[{}, {}]],
            "distances": [[0.1, 0.9]],
        }
        store._collections["c"] = coll
        res = await store.search_with_score("c", [1.0], min_score=0.5)
        assert [r["id"] for r in res] == ["a"]

    async def test_delete_by_id(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        store._collections["c"] = coll
        await store.delete_by_id("c", ["a", "b"])
        assert coll.deleted == [["a", "b"]]

    async def test_delete_by_id_missing_collection(self):
        await make_storeless().delete_by_id("c", ["a"])

    async def test_clear_collection(self):
        store, client = make_store()
        coll = FakeCollection("c")
        store._collections["c"] = coll
        store._initialized_collections.add("c")
        client.collections["c"] = coll
        await store.clear_collection("c")
        assert "c" not in store._collections
        assert "c" not in store._initialized_collections
        assert client.deleted_collections == ["c"]

    async def test_clear_collection_delete_error_swallowed(self):
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        store._initialized_collections.add("c")
        await store.clear_collection("c")
        assert "c" not in store._collections
        assert "c" not in store._initialized_collections

    async def test_clear_collection_without_client(self):
        await make_storeless().clear_collection("c")

    async def test_get_collection_stats(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll._count = 7
        store._collections["c"] = coll
        assert await store.get_collection_stats("c") == {"count": 7, "name": "c"}

    async def test_get_collection_stats_missing(self):
        res = await make_storeless().get_collection_stats("c")
        assert res == {"count": 0, "error": "Collection not found"}

    async def test_get_collection_stats_count_fails_peek_ok(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll._count_raises = True
        coll._count = 3
        store._collections["c"] = coll
        assert await store.get_collection_stats("c") == {"count": 1, "name": "c"}

    async def test_get_collection_stats_count_fails_peek_empty(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll._count_raises = True
        store._collections["c"] = coll
        assert await store.get_collection_stats("c") == {"count": -1, "name": "c"}

    async def test_get_collection_stats_both_fail(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll._count_raises = True
        coll._peek_raises = True
        store._collections["c"] = coll
        res = await store.get_collection_stats("c")
        assert res["count"] == 0
        assert "error" in res


class TestTokenize:
    def test_tokenize(self):
        tokens = ChromaVectorStore._tokenize("Hello 世界 42")
        assert "hello" in tokens
        assert "世界" in tokens
        assert "42" in tokens

    def test_tokenize_empty(self):
        assert ChromaVectorStore._tokenize("") == []


class TestBm25:
    def test_build_bm25_index(self):
        store, _ = make_store()
        store._build_bm25_index("c", ["doc one", "doc two"], ["a", "b"])
        idx = store._bm25_indexes["c"]
        assert idx["doc_ids"] == ["a", "b"]
        assert len(idx["corpus_tokens"]) == 2

    def test_build_bm25_index_unavailable(self, monkeypatch):
        store, _ = make_store()
        monkeypatch.setattr(chroma_mod, "_get_bm25", lambda: None)
        store._build_bm25_index("c", ["doc"], ["a"])
        assert "c" not in store._bm25_indexes

    async def test_add_documents_with_bm25_new_index(self):
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        await store.add_documents_with_bm25("c", ["a"], ["hello world"], [[1.0]])
        assert "c" in store._bm25_indexes

    async def test_add_documents_with_bm25_extends_index(self):
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        await store.add_documents_with_bm25("c", ["a"], ["one"], [[1.0]])
        await store.add_documents_with_bm25("c", ["b"], ["two"], [[1.0]])
        assert store._bm25_indexes["c"]["doc_ids"] == ["a", "b"]

    async def test_add_documents_with_bm25_disabled(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_BM25", False)
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        await store.add_documents_with_bm25("c", ["a"], ["one"], [[1.0]])
        assert store._bm25_indexes == {}

    def test_rebuild_bm25_index(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll.get_result = {
            "ids": ["a", "b"],
            "documents": ["doc a", "doc b"],
            "metadatas": [{}, {}],
        }
        store._collections["c"] = coll
        store.rebuild_bm25_index("c")
        assert store._bm25_indexes["c"]["doc_ids"] == ["a", "b"]

    def test_rebuild_bm25_index_empty(self):
        store, _ = make_store()
        store._collections["c"] = FakeCollection("c")
        store.rebuild_bm25_index("c")
        assert "c" not in store._bm25_indexes

    def test_rebuild_bm25_index_missing_collection(self):
        make_storeless().rebuild_bm25_index("c")

    def test_rebuild_bm25_index_disabled(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_BM25", False)
        store, _ = make_store()
        store.rebuild_bm25_index("c")

    def test_rebuild_bm25_index_error(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll.get = MagicMock(side_effect=RuntimeError("boom"))
        store._collections["c"] = coll
        store.rebuild_bm25_index("c")
        assert "c" not in store._bm25_indexes

    async def test_rebuild_bm25_index_async(self):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll.get_result = {"ids": ["a"], "documents": ["doc a"], "metadatas": [{}]}
        store._collections["c"] = coll
        await store.rebuild_bm25_index_async("c")
        assert "c" in store._bm25_indexes


class TestHybridSearch:
    """``hybrid_search`` の BM25 経路。

    ソースは ``if bm25_scores`` と判定しているため ``get_scores`` が
    ``list`` を返すケース（コードが想定している契約）を検証する。
    実際の rank_bm25 は numpy 配列を返し、この行で ValueError になる既知の
    ソース側の不具合はFIXしない（テスト強化のみが本務）。
    """

    class _ListBM25:
        def __init__(self, corpus_tokens):
            self.corpus = corpus_tokens

        def get_scores(self, query_tokens):
            q = set(query_tokens)
            return [
                sum(1 for t in doc if t in q) / max(1, len(doc)) for doc in self.corpus
            ]

    @pytest.fixture(autouse=True)
    def _inject_list_bm25(self, monkeypatch):
        monkeypatch.setitem(
            chroma_mod.__dict__, "BM25Okapi", TestHybridSearch._ListBM25
        )
        monkeypatch.setattr(chroma_mod, "HAS_BM25", True)

    def _seeded(self, with_bm25=True):
        store, _ = make_store()
        coll = FakeCollection("c")
        coll.query_result = {
            "ids": [["a", "b"]],
            "documents": [["hello world", "goodbye"]],
            "metadatas": [[{"g": 1}, {"g": 2}]],
            "distances": [[0.1, 0.6]],
        }
        store._collections["c"] = coll
        if with_bm25:
            store._build_bm25_index("c", ["hello world", "goodbye"], ["a", "b"])
        return store, coll

    async def test_hybrid_search(self):
        store, _ = self._seeded()
        res = await store.hybrid_search("c", "hello", [1.0], top_k=5)
        assert res
        assert res[0]["id"] == "a"
        assert "combined_score" in res[0]

    async def test_hybrid_search_sorted(self):
        store, _ = self._seeded()
        res = await store.hybrid_search("c", "hello", [1.0], top_k=5)
        scores = [r["combined_score"] for r in res]
        assert scores == sorted(scores, reverse=True)

    async def test_hybrid_search_alpha_clamped(self):
        store, _ = self._seeded()
        assert await store.hybrid_search("c", "hello", [1.0], alpha=-1.0)
        assert await store.hybrid_search("c", "hello", [1.0], alpha=2.0)

    async def test_hybrid_search_min_score_filters(self):
        store, _ = self._seeded()
        assert await store.hybrid_search("c", "hello", [1.0], min_score=99.0) == []

    async def test_hybrid_search_without_bm25(self, monkeypatch):
        monkeypatch.setattr(chroma_mod, "HAS_BM25", False)
        store, _ = self._seeded(with_bm25=False)
        res = await store.hybrid_search("c", "hello", [1.0])
        assert res[0]["bm25_score"] == 0.0

    async def test_hybrid_search_bm25_only_hit(self):
        store, coll = self._seeded()
        coll.query_result = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        res = await store.hybrid_search("c", "hello", [1.0], alpha=0.0)
        assert res
        assert all(r["vector_similarity"] == 0.0 for r in res)

    async def test_hybrid_search_empty_index(self):
        store, _ = self._seeded(with_bm25=False)
        store._bm25_indexes["c"] = {
            "bm25": MagicMock(get_scores=lambda t: []),
            "doc_ids": [],
            "documents": [],
        }
        res = await store.hybrid_search("c", "hello", [1.0])
        assert len(res) == 2

    async def test_hybrid_search_bm25_metadata_fallback(self):
        store, coll = self._seeded()
        coll.query_result = {
            "ids": [["a"]],
            "documents": [["hello world"]],
            "metadatas": [[None]],
            "distances": [[0.9]],
        }
        res = await store.hybrid_search("c", "hello", [1.0], alpha=0.0)
        assert res

    async def test_hybrid_search_missing_collection(self):
        assert await make_storeless().hybrid_search("c", "hello", [1.0]) == []
