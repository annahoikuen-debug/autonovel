"""ChromaDB 互換のインメモリクライアント（Chroma 不在時のフォールバック）。

なぜこのモジュールが存在するか
---------------------------
`src/services/rag/context_retriever.py` は `chroma_client is None` のとき
ChromaDB 互換のクライアントへフォールバックする。従来は
`from src.services.vector_store.in_memory import InMemoryVectorStore` を
読み込んでいたが、**そのクラスは同モジュールに存在しない**
（`in_memory.py` にあるのは `InMemoryFallbackStore`）。

そのため Chroma を用意できない環境では、このフォールバック経路が
`ImportError` で落ちていた（本番で Chroma 無効時に到達する）。

`InMemoryFallbackStore` は `BaseVectorStore` 実装
（`search` / `add_documents` / `hybrid_search`）であり、
`context_retriever` が要求する **Chroma の Collection 互換 API**
（`upsert` / `get(ids=...)` / `query` / `update`）とは形状が異なるため
そのまま差し替えられない。

方針（2026-10-05 の利用者判断）: **呼び出し側を変更せず**、
Chroma 互換インターフェースを持つインメモリ実装を別モジュールで提供する。

検索は embedding ではなく**トークン重なり（Jaccard）**による簡易スコアリングであり、
本番の Chroma（ベクトル検索）とは検索精度が異なる。これは
「Chroma が無い環境で動作する」ためのフェールバックであり、
検索品質を代替するものではありません。
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["InMemoryVectorStore", "InMemoryCollection"]

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    """簡易トークナイザ。

    非 ASCII の語は 2 文字 bigram 分割も重ねて重なりを補強する。
    非 ASCII の語は 2 文字 bigram 分割も重ねて重なりを補強する。
    """
    tokens = set(_WORD_RE.findall(text.lower()))
    for word in _WORD_RE.findall(text):
        if len(word) > 1 and not word.isascii():
            tokens.update(word[i : i + 2] for i in range(len(word) - 1))
    return tokens


def _jaccard(a: str, b: str) -> float:
    """トークン集合の Jaccard 係数（0.0〜1.0）。"""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _matches_where(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
    """Chroma の `where` サブセット（`$ne` / `$eq` / `$in`）を評価する。"""
    if not where:
        return True
    for key, cond in where.items():
        actual = metadata.get(key)
        if isinstance(cond, dict):
            if "$ne" in cond and actual == cond["$ne"]:
                return False
            if "$eq" in cond and actual != cond["$eq"]:
                return False
            if "$in" in cond and actual not in cond["$in"]:
                return False
        elif actual != cond:
            return False
    return True


class InMemoryCollection:
    """Chroma の `Collection` 互換インメモリ実装。"""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None):
        self.name = name
        self.metadata = dict(metadata or {})
        self._records: dict[str, dict[str, Any]] = {}

    def __len__(self) -> int:
        return len(self._records)

    def add(
        self,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """新規追加（既存 ID は上書きしない）。"""
        for i, doc_id in enumerate(ids):
            if doc_id in self._records:
                continue
            self._records[doc_id] = {
                "document": documents[i] if documents else "",
                "metadata": dict(metadatas[i]) if metadatas else {},
            }

    def upsert(
        self,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """追加または更新。"""
        for i, doc_id in enumerate(ids):
            prev = self._records.get(doc_id, {})
            self._records[doc_id] = {
                "document": documents[i] if documents else prev.get("document", ""),
                "metadata": dict(metadatas[i]) if metadatas else dict(prev.get("metadata", {})),
            }

    def update(
        self,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """既存レコードを部分更新する。"""
        for i, doc_id in enumerate(ids):
            rec = self._records.get(doc_id)
            if rec is None:
                continue
            if documents:
                rec["document"] = documents[i]
            if metadatas:
                rec["metadata"].update(metadatas[i])

    def get(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, list[Any]]:
        """条件一致のレコードを取り出す（Chroma 互換の戻り値形状）。"""
        if ids is not None:
            found_ids = [i for i in ids if i in self._records]
            targets = [self._records[i] for i in found_ids]
        else:
            targets = [
                r for r in self._records.values() if _matches_where(r["metadata"], where)
            ]
            found_ids = list(self._records)[: len(targets)]
            # 順序を保持するため、ID を取得し直す
            found_ids = [
                doc_id
                for doc_id, rec in self._records.items()
                if _matches_where(rec["metadata"], where)
            ]

        return {
            "ids": found_ids,
            "documents": [r["document"] for r in targets],
            "metadatas": [r["metadata"] for r in targets],
        }

    def query(
        self,
        query_texts: list[str],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, list[Any]]:
        """トークン重なりによる簡易類似検索（Chroma 互換の戻り値形状）。"""
        out: dict[str, list[Any]] = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        if not query_texts:
            return out

        query = query_texts[0]
        scored = [
            (1.0 - _jaccard(query, rec["document"]), doc_id, rec)
            for doc_id, rec in self._records.items()
            if _matches_where(rec["metadata"], where)
        ]
        scored.sort(key=lambda t: t[0])

        for distance, doc_id, rec in scored[:n_results]:
            out["ids"][0].append(doc_id)
            out["documents"][0].append(rec["document"])
            out["metadatas"][0].append(rec["metadata"])
            out["distances"][0].append(max(0.0, min(1.0, distance)))
        return out

    def delete(
        self, ids: list[str] | None = None, where: dict[str, Any] | None = None
    ) -> None:
        """削除。"""
        if ids is not None:
            for i in ids:
                self._records.pop(i, None)
            return
        for doc_id in [
            d for d, r in self._records.items() if _matches_where(r["metadata"], where)
        ]:
            self._records.pop(doc_id, None)


class InMemoryVectorStore:
    """Chroma の `Client` 互換インメモリ実装。

    必要なのは `get_collection(name)` と
    `create_collection(name=..., embedding_function=..., metadata=...)` の 2 つ。
    `embedding_function` は受け取るが本実装では使用しない（§docstring 参照）。
    """

    def __init__(
        self,
        max_items_per_collection: int = 10000,
        enable_graph: bool = True,
    ):
        self.max_items_per_collection = max_items_per_collection
        self.enable_graph = enable_graph
        self._collections: dict[str, InMemoryCollection] = {}

    def get_collection(self, name: str, **kwargs: Any) -> InMemoryCollection:
        """既存コレクションを返す。無ければ**例外を投げる**（Chroma と同一挙動）。

        `context_retriever._get_or_create_collection` は
        `get_collection()` が例外を投げることを前提に
        `create_collection()` へフォールバックしている::

            try:
                collection = self.chroma_client.get_collection(name)
            except Exception:
                collection = self.chroma_client.create_collection(...)

        None を返すと `collection` が None のまま通過し、
        直後の `collection.upsert(...)` で AttributeError になる。
         したがって「存在しない」を例外で表現する（Chroma と同じ）。
        """
        if name not in self._collections:
            raise KeyError(f"Collection {name} does not exist")
        return self._collections[name]

    def get_or_create_collection(
        self,
        name: str,
        embedding_function: Any = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> InMemoryCollection:
        """取得または作成。"""
        if name not in self._collections:
            self._collections[name] = InMemoryCollection(name, metadata)
        return self._collections[name]

    def create_collection(
        self,
        name: str,
        embedding_function: Any = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> InMemoryCollection:
        """コレクションを作成（既存なら返す）。"""
        if name not in self._collections:
            self._collections[name] = InMemoryCollection(name, metadata)
        return self._collections[name]

    def list_collections(self) -> list[str]:
        """コレクション名の一覧。"""
        return list(self._collections)

    def delete_collection(self, name: str) -> None:
        """コレクションを削除。"""
        self._collections.pop(name, None)

    def reset(self) -> None:
        """全コレクションを破棄する（テスト用）。"""
        self._collections.clear()
