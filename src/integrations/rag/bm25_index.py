"""Episode-scoped BM25 sparse index over ``ChapterChunk`` (Plan R5 C1).

book_id ごとに ``ChapterChunk`` を取得し ``BM25SparseRetriever`` を構築・キャッシュする。
SQLite フォールバック経路の恣意的 1000 チャンク制限を吸収し、
book スコープの全チャンクを索引化する（上限 ``RAG_BM25_MAX_DOCS``）。
インデックス構築に失敗・上限超過のときは ``None`` を返し、呼び出し側は dense 単一検索にフォールバックする（fail-open）。
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

from src.backend.config import settings
from src.infrastructure.database.models.chapter import Chapter
from src.infrastructure.database.models.chunk import ChapterChunk
from src.integrations.rag.rag_service import SearchResult
from src.integrations.rag.sparse_retriever import BM25SparseRetriever

logger = logging.getLogger(__name__)

_MAX_CACHE_ENTRIES = 32


class EpisodeBM25Index:
    """book_id スコープの BM25 索引。キャッシュ付きで繰り返し構築を避ける。"""

    def __init__(self, max_docs: int | None = None) -> None:
        self.max_docs = max_docs or settings.RAG_BM25_MAX_DOCS
        self._cache: "OrderedDict[str, BM25SparseRetriever | None]" = OrderedDict()
        self._max_entries = _MAX_CACHE_ENTRIES

    def get(self, session: Any, book_id: int) -> BM25SparseRetriever | None:
        """book_id スコープの BM25SparseRetriever を返す。構築不可なら None。"""
        key = str(book_id)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        try:
            rows = (
                session.query(ChapterChunk)
                .join(Chapter, ChapterChunk.chapter_id == Chapter.id)
                .filter(Chapter.book_id == book_id)
                .order_by(ChapterChunk.created_at.asc())
                .all()
            )
        except Exception as e:
            logger.warning(f"EpisodeBM25Index: ChapterChunk 取得失敗 book_id={book_id}: {e}")
            self._evict_and_store(key, None)
            return None

        if not rows:
            self._evict_and_store(key, None)
            return None

        if len(rows) > self.max_docs:
            logger.warning(
                f"EpisodeBM25Index: book_id={book_id} chunks={len(rows)} > max_docs={self.max_docs}; "
                f"dense fallback"
            )
            self._evict_and_store(key, None)
            return None

        documents = [
            {
                "id": str(getattr(r, "id", "")),
                "content": r.content or "",
                "metadata": dict(r.chunk_metadata or {}),
            }
            for r in rows
            if getattr(r, "content", None)
        ]

        retriever = BM25SparseRetriever()
        retriever.index_documents(documents)
        self._evict_and_store(key, retriever)
        logger.debug(
            f"EpisodeBM25Index: built book_id={book_id} docs={len(documents)} max_docs={self.max_docs}"
        )
        return retriever

    def search(
        self, session: Any, book_id: int, query: str, top_k: int
    ) -> list[SearchResult]:
        """book_id スコープで BM25 検索を実行し ``SearchResult`` 列を返す。"""
        retriever = self.get(session, book_id)
        if retriever is None:
            return []
        return retriever.search(query, top_k=top_k)

    def _evict_and_store(self, key: str, value: BM25SparseRetriever | None) -> None:
        if len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)
        self._cache[key] = value
