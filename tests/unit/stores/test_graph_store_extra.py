"""src/stores/graph_store.py の追加テスト（kuzu 未導入環境）。"""
from __future__ import annotations

import sys
import types

import pytest

from src.stores.graph_store import (
    GraphStore,
    InMemoryGraphStore,
    KuzuGraphStore,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def has_next(self):
        return bool(self._rows)

    def get_next(self):
        return self._rows.pop(0)


class _FakeConnection:
    def __init__(self, results=None):
        self.executed = []
        self.results = results or []

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if self.results:
            return self.results.pop(0)
        return _FakeResult([])


@pytest.fixture
def fake_kuzu(monkeypatch):
    module = types.ModuleType("kuzu")

    class Database:
        def __init__(self, path):
            self.path = path

    module.Database = Database
    module.Connection = lambda db: _FakeConnection()
    monkeypatch.setitem(sys.modules, "kuzu", module)
    return module


class TestAbstractGraphStore:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            GraphStore()  # type: ignore[abstract]

    def test_in_memory_implements_interface(self):
        assert isinstance(InMemoryGraphStore(), GraphStore)


class TestInMemoryGraphStore:
    def test_upsert_and_latest(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {"affection": 0.1, "beat_id": "b1"})
        s.upsert_edge("A", "B", {"affection": 0.2, "beat_id": "b2"})
        latest = s.get_latest_edge("A", "B")
        assert latest["affection"] == 0.2
        assert "timestamp" in latest

    def test_latest_missing(self):
        assert InMemoryGraphStore().get_latest_edge("X", "Y") is None

    def test_upsert_none_props(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {})
        assert "timestamp" in s.get_latest_edge("A", "B")

    def test_causal_path_direct(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {"cause": "betrayal", "episode": 1, "affection": -1.0})
        path = s.query_causal_path("A", "B")
        assert path[0]["from"] == "A" and path[0]["to"] == "B"
        assert path[0]["cause"] == "betrayal"
        assert path[0]["episode"] == 1
        assert path[0]["emotions"] == {"affection": -1.0}

    def test_causal_path_multi_hop(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {"cause": "c1"})
        s.upsert_edge("B", "C", {"cause": "c2"})
        path = s.query_causal_path("A", "C")
        assert [p["to"] for p in path] == ["B", "C"]

    def test_causal_path_max_hops_exceeded(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {})
        s.upsert_edge("B", "C", {})
        assert s.query_causal_path("A", "C", max_hops=1) == []

    def test_causal_path_same_node(self):
        assert InMemoryGraphStore().query_causal_path("A", "A") == []

    def test_causal_path_not_found(self):
        assert InMemoryGraphStore().query_causal_path("A", "Z") == []

    def test_causal_path_avoids_cycles(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {})
        s.upsert_edge("B", "A", {})
        assert s.query_causal_path("A", "A") == []

    def test_get_all_edges(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {})
        all_e = s.get_all_edges()
        assert list(all_e.keys()) == [("A", "B")]

    def test_delete_all(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {})
        assert s.delete_edge("A", "B") is True
        assert s.get_latest_edge("A", "B") is None

    def test_delete_missing(self):
        assert InMemoryGraphStore().delete_edge("A", "B") is False

    def test_delete_by_beat_id(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {"beat_id": "b1"})
        s.upsert_edge("A", "B", {"beat_id": "b2"})
        assert s.delete_edge("A", "B", beat_id="b1") is True
        assert len(s.get_all_edges()[("A", "B")]) == 1

    def test_delete_by_beat_id_not_found(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {"beat_id": "b1"})
        assert s.delete_edge("A", "B", beat_id="zzz") is False

    def test_delete_last_beat_removes_key(self):
        s = InMemoryGraphStore()
        s.upsert_edge("A", "B", {"beat_id": "b1"})
        assert s.delete_edge("A", "B", beat_id="b1") is True
        assert s.get_all_edges() == {}


class TestKuzuGraphStoreUnavailable:
    def test_init_without_kuzu(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "kuzu", None)
        s = KuzuGraphStore()
        assert s._available is False
        assert s.upsert_edge("A", "B", {}) is None
        assert s.get_latest_edge("A", "B") is None
        assert s.query_causal_path("A", "B") == []
        assert s.delete_edge("A", "B") is False

    def test_init_failure_is_swallowed(self, monkeypatch):
        module = types.ModuleType("kuzu")

        class Database:
            def __init__(self, path):
                raise RuntimeError("boom")

        module.Database = Database
        module.Connection = lambda db: None
        monkeypatch.setitem(sys.modules, "kuzu", module)
        s = KuzuGraphStore()
        assert s._available is False

    def test_escape(self):
        assert KuzuGraphStore._escape("a'b") == "a\\'b"
        assert KuzuGraphStore._escape("a\\b") == "a\\\\b"


class TestKuzuGraphStoreWithFake:
    def _store(self, results=None, monkeypatch=None):
        conn = _FakeConnection([])
        module = types.ModuleType("kuzu")
        module.Database = lambda path: object()
        module.Connection = lambda db: conn
        (monkeypatch.setitem(sys.modules, "kuzu", module),)
        store = KuzuGraphStore()
        store._connection = conn
        store._available = True
        # クエリ結果はこの後に差し込む（スキーマ作成の execute には影響させない）
        conn.results = list(results or [])
        return store, conn

    def test_schema_created(self, monkeypatch):
        store, conn = self._store(monkeypatch=monkeypatch)
        assert any("CREATE NODE TABLE" in q for q, _ in conn.executed)

    def test_upsert_edge(self, monkeypatch):
        store, conn = self._store(monkeypatch=monkeypatch)
        store.upsert_edge("A", "B", {"affection": "0.5", "episode": "3"})
        merge_queries = [q for q, _ in conn.executed if q.startswith("MERGE")]
        assert len(merge_queries) == 2
        create = [p for q, p in conn.executed if "FEELS_TOWARD {" in q][-1]
        assert create["affection"] == 0.5
        assert create["episode"] == 3

    def test_get_latest_edge(self, monkeypatch):
        rows = [_FakeResult([(0.1, 0.2, 0.3, 0.4, 0.5, "c", 7, 1.0)])]
        store, _ = self._store(rows, monkeypatch=monkeypatch)
        out = store.get_latest_edge("A", "B")
        assert out["affection"] == 0.1 and out["cause"] == "c"

    def test_get_latest_edge_none(self, monkeypatch):
        store, _ = self._store([_FakeResult([])], monkeypatch=monkeypatch)
        assert store.get_latest_edge("A", "B") is None

    def test_query_causal_path(self, monkeypatch):
        rows = [_FakeResult([(["c1", "c2"], [1, 2])])]
        store, _ = self._store(rows, monkeypatch=monkeypatch)
        path = store.query_causal_path("A", "C")
        assert path[0]["from"] == "A"
        assert path[-1]["to"] == "C"
        assert path[0]["episode"] == 1

    def test_query_causal_path_none(self, monkeypatch):
        store, _ = self._store([_FakeResult([])], monkeypatch=monkeypatch)
        assert store.query_causal_path("A", "C") == []

    def test_delete_edge(self, monkeypatch):
        store, conn = self._store(monkeypatch=monkeypatch)
        assert store.delete_edge("A", "B") is True
        assert store.delete_edge("A", "B", beat_id="b1") is True

    def test_delete_edge_error(self, monkeypatch):
        store, conn = self._store(monkeypatch=monkeypatch)

        def boom(*args, **kwargs):
            raise RuntimeError("nope")

        conn.execute = boom
        assert store.delete_edge("A", "B") is False
