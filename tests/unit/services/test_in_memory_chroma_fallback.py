"""Chroma 互換シムのフォールバック経路テスト（回帰防止）。

何が起きたか
------------
`src/services/rag/context_retriever.py` は `chroma_client is None` のとき
Chroma 互換クライアントへフォールバックするが、従来は
`from src.services.vector_store.in_memory import InMemoryVectorStore` を
読んでいた。**そのクラスは同モジュールに存在しない**（`InMemoryFallbackStore` が
実体）ため、Chroma を用意できない環境では `ImportError` で落ちていた。

修正: `src/services/vector_store/in_memory_chroma.py` に
Chroma 互換インターフェース（`get_collection` / `create_collection`、
`Collection.upsert/get/query/update`）を持つ実装を追加し、
import 先をそちらに向ける。**呼び出し側は変更していない。**

本ファイルは fallback 経路が実際に機能することを固定する。
"""
from __future__ import annotations

import pytest


class TestInMemoryChromaShim:
    """シム自体の Chroma 互換性。"""

    @pytest.fixture
    def store(self):
        from src.services.vector_store.in_memory_chroma import InMemoryVectorStore

        return InMemoryVectorStore()

    def test_get_collection_raises_when_absent(self, store) -> None:
        """存在しないコレクションは例外を投げる（Chroma と同一）。

        `context_retriever._get_or_create_collection` は
        「`get_collection()` が例外を投げたら `create_collection()`」という
        前提で書かれているため、None を返すと後続が AttributeError になる。
        """
        with pytest.raises(KeyError):
            store.get_collection("nope")

    def test_create_collection_is_idempotent(self, store) -> None:
        """create を 2 回呼んでも同じインスタンスを返す。"""
        a = store.create_collection("c", metadata={"k": 1})
        b = store.create_collection("c")
        assert a is b

    def test_upsert_then_get(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(ids=["a"], documents=["文書A"], metadatas=[{"status": "open"}])
        got = c.get()
        assert got["ids"] == ["a"]
        assert got["documents"] == ["文書A"]
        assert got["metadatas"] == [{"status": "open"}]

    def test_get_with_ids_filter(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(ids=["a", "b"], documents=["A", "B"], metadatas=[{}, {}])
        got = c.get(ids=["b"])
        assert got["ids"] == ["b"]
        assert got["documents"] == ["B"]

    def test_upsert_overwrites_existing(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(ids=["a"], documents=["old"], metadatas=[{"v": 1}])
        c.upsert(ids=["a"], documents=["new"], metadatas=[{"v": 2}])
        got = c.get(ids=["a"])
        assert got["documents"] == ["new"]
        assert got["metadatas"] == [{"v": 2}]

    def test_update_merges_metadata(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(ids=["a"], documents=["A"], metadatas=[{"v": 1, "keep": True}])
        c.update(ids=["a"], metadatas=[{"v": 2}])
        meta = c.get(ids=["a"])["metadatas"][0]
        assert meta["v"] == 2
        assert meta["keep"] is True, "update は部分更新であり、他のキーは保持される"

    def test_query_respects_where_ne(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(
            ids=["open1", "resolved1"],
            documents=["未回収の伏線", ["回収済み"]][0],
            metadatas=[{"status": "open"}, {"status": "resolved"}],
        )
        got = c.query(query_texts=["伏線"], n_results=10, where={"status": {"$ne": "resolved"}})
        assert "open1" in got["ids"][0]
        assert "resolved1" not in got["ids"][0]

    def test_query_returns_distances_in_range(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(ids=["a"], documents=["同じテキスト"], metadatas=[{}])
        got = c.query(query_texts=["同じテキスト"], n_results=1)
        distance = got["distances"][0][0]
        assert 0.0 <= distance <= 1.0

    def test_query_ranks_identical_text_first(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(
            ids=["exact", "unrelated"],
            documents=["鍵の行方", "まったく違う話"],
            metadatas=[{}, {}],
        )
        got = c.query(query_texts=["鍵の行方"], n_results=2)
        assert got["ids"][0][0] == "exact"

    def test_delete(self, store) -> None:
        c = store.create_collection("c")
        c.upsert(ids=["a", "b"], documents=["A", "B"], metadatas=[{}, {}])
        c.delete(ids=["a"])
        assert c.get()["ids"] == ["b"]


class TestContextRetrieverFallback:
    """`context_retriever` の fallback 経路が実際に動くこと（最重要）。"""

    def test_module_imports_without_import_error(self) -> None:
        """fallback import が ImportError にならないこと。

        これが本次修正の核心。従来の
        `from ...in_memory import InMemoryVectorStore` は
        クラスが存在せず ImportError だった。
        """
        from src.services.vector_store.in_memory_chroma import InMemoryVectorStore

        assert InMemoryVectorStore is not None

    def test_old_module_has_no_in_memory_vector_store(self) -> None:
        """旧モジュールに同名クラスが無いことを明示する。

        将来 `in_memory.py` に同名クラスがあり并存させるのは
        どちらに import するか曖昧になるため、存在しないことを確認する。
        """
        from src.services.vector_store import in_memory

        assert not hasattr(in_memory, "InMemoryVectorStore"), (
            "in_memory.py に InMemoryVectorStore が復活している。"
            "どちらが正実装か曖昧になるため、どちらかに統一すること"
        )
        assert hasattr(in_memory, "InMemoryFallbackStore"), (
            "InMemoryFallbackStore が消えている（別テストが利用している）"
        )

    def test_fallback_path_end_to_end(self) -> None:
        """`chroma_client=None` の状態で upsert/get まで通ること。

        `context_retriever.ContextRetriever` を実際に構築し、
        `_get_or_create_collection` が ImportError せず、
        コレクションが利用できることを確認する。
        """
        from src.services.rag.context_retriever import LongFormContextRetriever

        retriever = LongFormContextRetriever.__new__(LongFormContextRetriever)
        retriever.chroma_client = None
        retriever.embedding_function = None
        retriever._collections = {}

        collection = retriever._get_or_create_collection(1)
        assert collection is not None
        assert collection.name == "novel_foreshadowings_book_1"

        # 2 回目は同じインスタンスが返る（キャッシュ）
        assert retriever._get_or_create_collection(1) is collection
        assert retriever._get_or_create_collection(2) is not collection

    def test_fallback_upsert_and_query(self) -> None:
        """fallback クライアントで upsert → query が通ること。"""
        from src.services.rag.context_retriever import LongFormContextRetriever

        retriever = LongFormContextRetriever.__new__(LongFormContextRetriever)
        retriever.chroma_client = None
        retriever.embedding_function = None
        retriever._collections = {}

        collection = retriever._get_or_create_collection(1)
        collection.upsert(
            ids=["F-001"],
            documents=["欠けた鍵の行方が分かった"],
            metadatas=[{"status": "open"}],
        )
        got = collection.query(query_texts=["鍵の行方"], n_results=1)
        assert "F-001" in got["ids"][0]
