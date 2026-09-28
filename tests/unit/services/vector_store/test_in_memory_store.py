"""Unit tests for src/services/vector_store/{base,in_memory}.py."""
import pytest

import src.services.vector_store.in_memory as im
from src.services.vector_store.base import (
    DEFAULT_COLLECTIONS,
    BaseVectorStore,
    CollectionConfig,
    CollectionType,
    VectorStoreProtocol,
)
from src.services.vector_store.in_memory import (
    InMemoryFallbackStore,
    _metadata_matches,
)

py = pytest


class TestBase:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseVectorStore()

    def test_subclass_must_implement_all(self):
        class Partial(BaseVectorStore):
            async def add_documents(self, *a, **k):
                pass

        with pytest.raises(TypeError):
            Partial()

    def test_concrete_subclass_works(self):
        class Impl(BaseVectorStore):
            async def add_documents(self, *a, **k):
                pass

            async def search(self, *a, **k):
                return []

            async def search_with_score(self, *a, **k):
                return []

            async def delete_by_id(self, *a, **k):
                pass

            async def clear_collection(self, *a, **k):
                pass

        assert Impl() is not None

    def test_protocol_importable(self):
        assert VectorStoreProtocol is not None

    def test_collection_types(self):
        assert CollectionType.SEMANTIC_CACHE.value == "semantic_cache"
        assert CollectionType.EPISODE_MEMORY.value == "episode_memory"

    def test_collection_config_defaults(self):
        c = CollectionConfig(name="x")
        assert c.space == "cosine"
        assert c.description == ""
        assert c.hnsw_params["hnsw:M"] == 16

    def test_collection_config_get_metadata(self):
        c = CollectionConfig(name="x", space="l2", description="d")
        meta = c.get_metadata()
        assert meta["hnsw:space"] == "l2"
        assert meta["description"] == "d"
        assert meta["hnsw:search_ef"] == 50

    def test_hnsw_params_not_shared(self):
        a = CollectionConfig(name="a")
        b = CollectionConfig(name="b")
        a.hnsw_params["hnsw:M"] = 999
        assert b.hnsw_params["hnsw:M"] == 16

    def test_default_collections(self):
        assert set(DEFAULT_COLLECTIONS) == set(CollectionType)
        for cfg in DEFAULT_COLLECTIONS.values():
            assert cfg.name
            assert cfg.description


class TestMetadataMatches:
    def test_empty_where(self):
        assert _metadata_matches({"a": 1}, {}) is True
        assert _metadata_matches({"a": 1}, None) is True

    def test_match(self):
        assert _metadata_matches({"a": 1, "b": 2}, {"a": 1}) is True

    def test_mismatch(self):
        assert _metadata_matches({"a": 1}, {"a": 2}) is False

    def test_missing_key(self):
        assert _metadata_matches({"a": 1}, {"z": 1}) is False


class TestCosine:
    def test_identical(self):
        assert InMemoryFallbackStore._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0

    def test_orthogonal(self):
        assert InMemoryFallbackStore._cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_opposite(self):
        assert InMemoryFallbackStore._cosine([1.0, 0.0], [-1.0, 0.0]) == -1.0

    def test_length_mismatch(self):
        assert InMemoryFallbackStore._cosine([1.0], [1.0, 2.0]) == 0.0

    def test_empty(self):
        assert InMemoryFallbackStore._cosine([], []) == 0.0
        assert InMemoryFallbackStore._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestTokenize:
    def test_mixed(self):
        tokens = InMemoryFallbackStore._tokenize("Hello世界 123")
        assert "hello" in tokens
        assert "世界" in tokens
        assert "123" in tokens

    def test_empty(self):
        assert InMemoryFallbackStore._tokenize("") == []


class TestInMemoryFallbackStoreBasics:
    def test_init_defaults(self):
        s = InMemoryFallbackStore()
        assert s._max == 10000
        assert s._data == {}
        assert s._bm25_indexes == {}

    def test_init_max_clamped(self):
        assert InMemoryFallbackStore(max_items_per_collection=0)._max == 1
        assert InMemoryFallbackStore(max_items_per_collection=-5)._max == 1

    def test_graph_flag(self):
        assert InMemoryFallbackStore(enable_graph=False)._enable_graph is False

    async def test_add_documents(self):
        s = InMemoryFallbackStore()
        await s.add_documents(
            "c", ["a", "b"], ["doc a", "doc b"], [[1.0, 0.0], [0.0, 1.0]],
            [{"k": 1}, {"k": 2}],
        )
        assert len(s._data["c"]) == 2
        assert s._data["c"][0][3] == {"k": 1}

    async def test_add_documents_no_ids(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", [], [], [])
        assert "c" not in s._data

    async def test_add_documents_without_metadatas(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a"], ["doc"], [[1.0]])
        assert s._data["c"][0][3] == {}

    async def test_add_documents_fewer_metadatas(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a", "b"], ["x", "y"], [[1.0], [1.0]], [{"k": 1}])
        assert s._data["c"][1][3] == {}

    async def test_fifo_trim(self):
        s = InMemoryFallbackStore(max_items_per_collection=2)
        await s.add_documents("c", ["a", "b", "c"], ["1", "2", "3"], [[1.0]] * 3)
        assert [d[0] for d in s._data["c"]] == ["b", "c"]

    async def test_search(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a", "b"], ["x", "y"], [[1.0, 0.0], [0.0, 1.0]])
        res = await s.search("c", [1.0, 0.0], top_k=2)
        assert res[0]["id"] == "a"
        assert res[0]["similarity"] == 1.0
        assert res[0]["distance"] == 0.0
        assert res[0]["content"] == "x"

    async def test_search_empty_collection(self):
        assert await InMemoryFallbackStore().search("nope", [1.0]) == []

    async def test_search_with_where(self):
        s = InMemoryFallbackStore()
        await s.add_documents(
            "c", ["a", "b"], ["x", "y"], [[1.0], [1.0]], [{"g": 1}, {"g": 2}]
        )
        res = await s.search("c", [1.0], where={"g": 2})
        assert [r["id"] for r in res] == ["b"]

    async def test_search_top_k_zero(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a"], ["x"], [[1.0]])
        assert await s.search("c", [1.0], top_k=0) == []

    async def test_search_with_score(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a", "b"], ["x", "y"], [[1.0, 0.0], [0.0, 1.0]])
        res = await s.search_with_score("c", [1.0, 0.0], top_k=5)
        assert res[0]["id"] == "a"

    async def test_search_with_score_min_score_filters(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a", "b"], ["x", "y"], [[1.0, 0.0], [0.0, 1.0]])
        res = await s.search_with_score("c", [1.0, 0.0], min_score=0.5)
        assert [r["id"] for r in res] == ["a"]

    async def test_search_with_score_where(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a", "b"], ["x", "y"], [[1.0], [1.0]], [{"g": 1}, {"g": 2}])
        res = await s.search_with_score("c", [1.0], where={"g": 9})
        assert res == []

    async def test_search_with_score_empty(self):
        assert await InMemoryFallbackStore().search_with_score("x", [1.0]) == []

    async def test_delete_by_id(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a", "b"], ["x", "y"], [[1.0], [1.0]])
        await s.delete_by_id("c", ["a"])
        assert [d[0] for d in s._data["c"]] == ["b"]

    async def test_delete_by_id_missing_collection(self):
        s = InMemoryFallbackStore()
        await s.delete_by_id("nope", ["a"])
        assert "nope" not in s._data

    async def test_delete_all_documents_drops_bm25_index(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a"], ["x"], [[1.0]])
        assert "c" in s._bm25_indexes
        await s.delete_by_id("c", ["a"])
        assert "c" not in s._bm25_indexes
        assert s._data["c"] == []

    async def test_delete_keeps_bm25_when_others_remain(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a", "b"], ["x", "y"], [[1.0], [1.0]])
        await s.delete_by_id("c", ["a"])
        assert "c" in s._bm25_indexes

    async def test_delete_from_bm25_collection_not_indexed(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a"], ["x"], [[1.0]])
        del s._bm25_indexes["c"]
        await s.delete_by_id("c", ["a"])
        assert s._data["c"] == []

    async def test_clear_collection(self):
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a"], ["x"], [[1.0]])
        await s.clear_collection("c")
        assert "c" not in s._data
        assert "c" not in s._bm25_indexes

    async def test_clear_collection_missing(self):
        await InMemoryFallbackStore().clear_collection("nope")

    async def test_clear_collection_without_graph(self):
        s = InMemoryFallbackStore(enable_graph=False)
        await s.add_documents("c", ["a"], ["x"], [[1.0]])
        await s.clear_collection("c")
        assert "c" not in s._data


class TestHybridSearch:
    async def _seed(self, alpha_graph=True):
        s = InMemoryFallbackStore()
        await s.add_documents(
            "c",
            ["a", "b", "c"],
            [" heroes  heroes journey", " villain arc", " unrelated text"],
            [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]],
        )
        return s

    async def test_basic(self):
        s = await self._seed()
        res = await s.hybrid_search("c", "heroes", [1.0, 0.0], top_k=3)
        assert res
        assert all("combined_score" in r for r in res)
        assert res[0]["id"] in ("a", "b", "c")

    async def test_sorted_descending(self):
        s = await self._seed()
        res = await s.hybrid_search("c", "heroes", [1.0, 0.0], top_k=3)
        scores = [r["combined_score"] for r in res]
        assert scores == sorted(scores, reverse=True)

    async def test_alpha_clamped(self):
        s = await self._seed()
        low = await s.hybrid_search("c", "heroes", [1.0, 0.0], alpha=-5.0)
        high = await s.hybrid_search("c", "heroes", [1.0, 0.0], alpha=5.0)
        assert low and high

    async def test_where_filter(self):
        s = InMemoryFallbackStore()
        await s.add_documents(
            "c", ["a", "b"], ["heroes", "other"], [[1.0], [1.0]], [{"g": 1}, {"g": 2}]
        )
        res = await s.hybrid_search("c", "heroes", [1.0], where={"g": 2})
        assert all(r["metadata"].get("g") == 2 for r in res)

    async def test_min_score_filters_everything(self):
        s = await self._seed()
        res = await s.hybrid_search("c", "heroes", [1.0, 0.0], min_score=10.0)
        assert res == []

    async def test_without_bm25(self, monkeypatch):
        monkeypatch.setattr(im, "HAS_BM25", False)
        s = InMemoryFallbackStore()
        await s.add_documents("c", ["a"], ["x"], [[1.0]])
        res = await s.hybrid_search("c", "x", [1.0])
        assert [r["id"] for r in res] == ["a"]
        assert res[0]["bm25_score"] == 0.0

    async def test_collection_without_index(self, monkeypatch):
        monkeypatch.setattr(im, "HAS_BM25", True)
        s = InMemoryFallbackStore()
        res = await s.hybrid_search("missing", "x", [1.0])
        assert res == []

    async def test_zero_bm25_scores_skipped(self, monkeypatch):
        s = await self._seed()
        monkeypatch.setattr(
            s._bm25_indexes["c"]["bm25"], "get_scores", lambda t: [0.0, 0.0, 0.0]
        )
        res = await s.hybrid_search("c", "zzzz", [1.0, 0.0])
        assert all(r["bm25_score"] == 0.0 for r in res)

    async def test_normalization_range_fallback(self, monkeypatch):
        s = await self._seed()
        monkeypatch.setattr(
            s._bm25_indexes["c"]["bm25"], "get_scores", lambda t: [2.0, 2.0, 2.0]
        )
        res = await s.hybrid_search("c", "heroes", [1.0, 0.0])
        assert res

    async def test_bm25_only_hit(self, monkeypatch):
        s = await self._seed()
        monkeypatch.setattr(
            s._bm25_indexes["c"]["bm25"],
            "get_scores",
            lambda t: [0.0, 0.0, 5.0],
        )
        res = await s.hybrid_search("c", "unrelated", [1.0, 0.0], top_k=3)
        ids = [r["id"] for r in res]
        assert "c" in ids

    async def test_top_k_limit(self):
        s = await self._seed()
        res = await s.hybrid_search("c", "heroes", [1.0, 0.0], top_k=1)
        assert len(res) == 1


class TestGraph:
    def _seed(self):
        return InMemoryFallbackStore()

    async def test_entities_and_relations(self):
        s = self._seed()
        await s.add_documents(
            "c",
            ["a"],
            ["doc"],
            [[1.0]],
            [
                {
                    "entities": ["Aoi", "Rin"],
                    "relations": [{"src": "Aoi", "dst": "Rin", "type": "friend"}],
                }
            ],
        )
        g = s._graphs["c"]
        assert set(g.nodes) == {"Aoi", "Rin"}
        assert g.has_edge("Aoi", "Rin")

    async def test_non_list_entities_ignored(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]], [{"entities": "notalist", "relations": "x"}]
        )
        assert len(s._graphs["c"].nodes) == 0

    async def test_malformed_relations_ignored(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]], [{"relations": [{"src": "X"}, "bad"]}]
        )
        assert len(s._graphs["c"].edges) == 0

    async def test_relation_default_type(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]], [{"relations": [{"src": "X", "dst": "Y"}]}]
        )
        assert s._graphs["c"].edges["X", "Y", 0]["rel_type"] == "related"

    async def test_get_neighbors(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]],
            [{"relations": [{"src": "A", "dst": "B", "type": "friend"}]}],
        )
        res = await s.get_neighbors("c", "A")
        assert res[0]["entity"] == "B"
        assert res[0]["relation"] == "friend"
        assert res[0]["depth"] == 1

    async def test_get_neighbors_reverse(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]],
            [{"relations": [{"src": "A", "dst": "B", "type": "friend"}]}],
        )
        res = await s.get_neighbors("c", "B")
        assert res[0]["entity"] == "A"
        assert res[0]["relation"].startswith("reverse_")

    async def test_get_neighbors_rel_type_filter(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]],
            [{"relations": [{"src": "A", "dst": "B", "type": "friend"}]}],
        )
        assert await s.get_neighbors("c", "A", rel_type="enemy") == []
        assert await s.get_neighbors("c", "A", rel_type="friend")

    async def test_get_neighbors_depth_limit(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]],
            [{"relations": [
                {"src": "A", "dst": "B", "type": "x"},
                {"src": "B", "dst": "C", "type": "x"},
            ]}],
        )
        d1 = await s.get_neighbors("c", "A", max_depth=1)
        assert {r["entity"] for r in d1} == {"B"}
        d2 = await s.get_neighbors("c", "A", max_depth=2)
        assert {r["entity"] for r in d2} == {"B", "C"}

    async def test_get_neighbors_limit(self):
        s = self._seed()
        await s.add_documents(
            "c", ["a"], ["doc"], [[1.0]],
            [{"relations": [{"src": "A", "dst": f"N{i}", "type": "x"} for i in range(5)]}],
        )
        assert len(await s.get_neighbors("c", "A", limit=2)) == 2

    async def test_get_neighbors_unknown_entity(self):
        assert await self._seed().get_neighbors("nope", "A") == []

    async def test_get_neighbors_graph_disabled(self):
        s = InMemoryFallbackStore(enable_graph=False)
        assert await s.get_neighbors("c", "A") == []

    async def test_clear_removes_graph(self):
        s = self._seed()
        await s.add_documents("c", ["a"], ["d"], [[1.0]], [{"entities": ["X"]}])
        await s.clear_collection("c")
        assert "c" not in s._graphs

    async def test_delete_removes_graph_nodes(self):
        s = self._seed()
        await s.add_documents("c", ["a"], ["d"], [[1.0]], [{"entities": ["A", "B"]}])
        await s.delete_by_id("c", ["A"])
        assert "A" not in s._graphs["c"].nodes


class TestCheckEntityValidity:
    async def test_graph_disabled(self):
        s = InMemoryFallbackStore(enable_graph=False)
        res = await s.check_entity_validity("c", "X")
        assert res == {
            "valid": True,
            "is_forbidden": False,
            "is_retired": False,
            "status": "active",
        }

    async def test_unknown_entity(self):
        res = await InMemoryFallbackStore().check_entity_validity("c", "X")
        assert res["valid"] is True
        assert res["status"] == "active"

    async def test_unknown_collection(self):
        res = await InMemoryFallbackStore().check_entity_validity("nope", "X")
        assert res["valid"] is True

    @pytest.mark.parametrize(
        "status,valid,forbidden,retired",
        [
            ("active", True, False, False),
            ("forbidden", False, True, False),
            ("banned", False, True, False),
            ("deprecated", False, True, False),
            ("dead", False, False, True),
            ("destroyed", False, False, True),
            ("sealed", False, False, True),
            ("retired", False, False, True),
        ],
    )
    async def test_status_mapping(self, status, valid, forbidden, retired):
        s = InMemoryFallbackStore()
        await s.add_documents(
            "c", ["a"], ["d"], [[1.0]], [{"entities": ["X"], "status": status}]
        )
        res = await s.check_entity_validity("c", "X")
        assert res["valid"] is valid
        assert res["is_forbidden"] is forbidden
        assert res["is_retired"] is retired
        assert res["status"] == status
        assert res["entity_name"] == "X"
