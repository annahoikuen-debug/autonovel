"""Tests for src/services/graphrag_sync_service.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


from src.services.graphrag_sync_service import GraphRAGSyncService


def make_repo(**misc_kwargs):
    repo = MagicMock()
    repo.misc = MagicMock()
    repo.misc.mark_delta_merged = AsyncMock(return_value=True)
    for k, v in misc_kwargs.items():
        setattr(repo.misc, k, AsyncMock(return_value=v))
    return repo


class TestMergeSettingDelta:
    async def test_no_repo(self):
        svc = GraphRAGSyncService()
        assert await svc.merge_setting_delta(1) is False

    async def test_delta_not_found(self):
        repo = make_repo(get_setting_delta=None)
        svc = GraphRAGSyncService(repo=repo)
        assert await svc.merge_setting_delta(7) is False

    async def test_already_merged(self):
        repo = make_repo(get_setting_delta={"id": 1, "merged_to_graphrag": True})
        svc = GraphRAGSyncService(repo=repo)
        assert await svc.merge_setting_delta(1) is True
        repo.misc.mark_delta_merged.assert_not_awaited()

    async def test_successful_merge(self):
        repo = make_repo(
            get_setting_delta={"id": 1, "merged_to_graphrag": False, "field_path": "a.b", "new_value": 3},
        )
        svc = GraphRAGSyncService(repo=repo, chroma_client=MagicMock(), kg_client=AsyncMock())
        assert await svc.merge_setting_delta(1) is True
        repo.misc.mark_delta_merged.assert_awaited_once_with(1)

    async def test_merge_failure_returns_false(self):
        repo = make_repo(get_setting_delta={"id": 1, "merged_to_graphrag": False})
        repo.misc.mark_delta_merged = AsyncMock(side_effect=RuntimeError("boom"))
        svc = GraphRAGSyncService(repo=repo)
        assert await svc.merge_setting_delta(1) is False


class TestMergePendingDeltas:
    async def test_no_repo(self):
        svc = GraphRAGSyncService()
        assert await svc.merge_pending_deltas(1) == 0

    async def test_batch(self):
        repo = make_repo(
            get_setting_deltas=[
                {"id": 1, "merged_to_graphrag": False},
                {"id": 2, "merged_to_graphrag": True},
                {"id": 3, "merged_to_graphrag": False},
            ]
        )
        svc = GraphRAGSyncService(repo=repo)
        svc.merge_setting_delta = AsyncMock(side_effect=[True, True])
        assert await svc.merge_pending_deltas(9) == 2

    async def test_batch_size_limit(self):
        repo = make_repo(
            get_setting_deltas=[{"id": i, "merged_to_graphrag": False} for i in range(5)]
        )
        svc = GraphRAGSyncService(repo=repo)
        svc.merge_setting_delta = AsyncMock(return_value=True)
        assert await svc.merge_pending_deltas(9, batch_size=2) == 2
        assert svc.merge_setting_delta.await_count == 2


class TestChromaUpdate:
    async def test_no_client(self):
        svc = GraphRAGSyncService()
        assert await svc._update_chromadb({"field_path": "a"}) is None

    async def test_collection_none(self):
        chroma = MagicMock()
        chroma.get_collection.return_value = None
        svc = GraphRAGSyncService(chroma_client=chroma)
        await svc._update_chromadb({"field_path": "a", "new_value": "v", "book_id": 1})
        chroma.get_collection.assert_called_once_with("bible_settings_1")

    async def test_delete_and_add(self):
        collection = MagicMock()
        chroma = MagicMock()
        chroma.get_collection.return_value = collection
        svc = GraphRAGSyncService(chroma_client=chroma)
        await svc._update_chromadb(
            {
                "field_path": "world.mana",
                "new_value": "10",
                "book_id": 2,
                "source": "user",
                "delta_type": "edit",
            }
        )
        collection.delete.assert_called_once_with(where={"field_path": "world.mana"})
        kwargs = collection.add.call_args.kwargs
        assert kwargs["documents"] == ["world.mana: 10"]
        assert kwargs["metadatas"][0]["book_id"] == 2
        assert kwargs["metadatas"][0]["source"] == "user"

    async def test_new_value_none_skips_add(self):
        collection = MagicMock()
        chroma = MagicMock()
        chroma.get_collection.return_value = collection
        svc = GraphRAGSyncService(chroma_client=chroma)
        await svc._update_chromadb({"field_path": "x", "new_value": None, "book_id": 1})
        collection.delete.assert_called_once()
        collection.add.assert_not_called()

    async def test_chroma_exception_swallowed(self):
        chroma = MagicMock()
        chroma.get_collection.side_effect = RuntimeError("nope")
        svc = GraphRAGSyncService(chroma_client=chroma)
        assert await svc._update_chromadb({"field_path": "x"}) is None


class TestKnowledgeGraphUpdate:
    async def test_no_client(self):
        svc = GraphRAGSyncService()
        assert await svc._update_knowledge_graph({"field_path": "a.b"}) is None

    async def test_query_built_for_dotted_path(self):
        kg = AsyncMock()
        svc = GraphRAGSyncService(kg_client=kg)
        await svc._update_knowledge_graph(
            {"field_path": "world_rules.magic.mana", "new_value": 5, "book_id": 3}
        )
        query, params = kg.execute_query.await_args.args
        assert params == {
            "book_id": 3,
            "node_type": "world_rules",
            "attr_path": "magic.mana",
            "new_value": 5,
        }
        assert "MATCH" in query

    async def test_single_segment_path_skipped(self):
        kg = AsyncMock()
        svc = GraphRAGSyncService(kg_client=kg)
        await svc._update_knowledge_graph({"field_path": "flat"})
        kg.execute_query.assert_not_awaited()

    async def test_kg_exception_swallowed(self):
        kg = AsyncMock()
        kg.execute_query.side_effect = RuntimeError("down")
        svc = GraphRAGSyncService(kg_client=kg)
        assert await svc._update_knowledge_graph({"field_path": "a.b"}) is None


class TestReindex:
    async def test_requires_repo_and_chroma(self):
        assert await GraphRAGSyncService().reindex_book_settings(1) is False
        assert await GraphRAGSyncService(repo=MagicMock()).reindex_book_settings(1) is False

    async def test_bible_missing(self):
        repo = MagicMock()
        repo.bible = MagicMock()
        repo.bible.get_bible = AsyncMock(return_value=None)
        svc = GraphRAGSyncService(repo=repo, chroma_client=MagicMock())
        assert await svc.reindex_book_settings(1) is False

    async def test_bible_model_dump(self):
        bible = MagicMock()
        bible.model_dump.return_value = {"a": {"b": 1}, "list": [1, 2], "empty": "  ", "none": None}
        repo = MagicMock()
        repo.bible = MagicMock()
        repo.bible.get_bible = AsyncMock(return_value=bible)
        collection = MagicMock()
        chroma = MagicMock()
        chroma.get_or_create_collection.return_value = collection
        svc = GraphRAGSyncService(repo=repo, chroma_client=chroma)
        assert await svc.reindex_book_settings(4) is True
        collection.delete.assert_called_once_with(where={"book_id": 4})
        assert collection.add.call_count == 2

    async def test_plain_dict_bible(self):
        repo = MagicMock()
        repo.bible = MagicMock()
        repo.bible.get_bible = AsyncMock(return_value={"x": "y"})
        collection = MagicMock()
        chroma = MagicMock()
        chroma.get_or_create_collection.return_value = collection
        svc = GraphRAGSyncService(repo=repo, chroma_client=chroma)
        assert await svc.reindex_book_settings(1) is True
        assert collection.add.call_count == 1

    async def test_reindex_exception(self):
        repo = MagicMock()
        repo.bible = MagicMock()
        repo.bible.get_bible = AsyncMock(side_effect=RuntimeError("x"))
        svc = GraphRAGSyncService(repo=repo, chroma_client=MagicMock())
        assert await svc.reindex_book_settings(1) is False


class TestFlattenDict:
    def test_flatten(self):
        svc = GraphRAGSyncService()
        out = svc._flatten_dict(
            {
                "a": {"b": {"c": 1}},
                "l": [1, {"x": 2}],
                "s": "str",
                "n": None,
            }
        )
        assert out["a.b.c"] == 1
        assert out["l"] == '[1, {"x": 2}]'
        assert out["s"] == "str"
        assert out["n"] is None

    def test_custom_separator(self):
        svc = GraphRAGSyncService()
        assert svc._flatten_dict({"a": {"b": 1}}, sep="/") == {"a/b": 1}

    def test_empty(self):
        assert GraphRAGSyncService()._flatten_dict({}) == {}
