"""Plan R5 C2: ReflectiveRAGService 構築ファクトリ.

``ReflectiveRAGService(rag_service=rag_service)`` の直接生成を廃止し、
本ファクトリ経由に一本化する。これにより hybrid / HyDE フラグの一元管理と、
``ReflectiveRAGService(`` の直接生成回帰防止テスト (T10) が可能になる。

フラグ全 OFF (既定) では従来と等価（dense 単一 + テンプレート reformulation）に振る舞う。
"""

from __future__ import annotations

import logging
from typing import Any

from src.backend.config import settings
from src.integrations.rag.bm25_index import EpisodeBM25Index
from src.integrations.rag.hybrid_retriever import HybridRetriever
from src.integrations.rag.query_reformulator import QueryReformulator
from src.integrations.rag.reflective_rag import ReflectiveRAGService

logger = logging.getLogger(__name__)


class _GraphRagDenseAdapter:
    """GraphRAGService を HybridRetriever の dense_retriever インターフェースに合わせるアダプタ.

    ``search(query, top_k)`` を提供し、内部で ``GraphRAGService.search_similar_chunks_sync`` を呼ぶ。
    ``session`` は後から (ReflectiveRAGService.retrieve_with_reflection 経由で) 注入される。
    """

    def __init__(self, rag_service: Any) -> None:
        self.rag_service = rag_service
        self.session: Any = None

    def search(self, query: str, top_k: int = 20) -> Any:
        if self.session is None:
            return []
        return self.rag_service.search_similar_chunks_sync(
            self.session, query=query, limit=top_k, min_score=0.0
        )


def build_reflective_rag(
    rag_service: Any,
    llm_adapter: Any = None,
) -> ReflectiveRAGService:
    """Plan R5: ReflectiveRAGService を構築する.

    - ``RAG_HYBRID_ENABLED=True``: dense(GraphRAG) + BM25(EpisodeBM25Index) を
      HybridRetriever(RRF k=60) で融合した hybrid_retriever を組み立てる。
    - ``RAG_HYDE_MODE="llm"``: LLM ベース QueryReformulator を組み立てる。
    - どちらも未設定/False: 従来と等価（hybrid_retriever=None、query_reformulator=None）。
    """
    hybrid_retriever: Any = None
    sparse_index: Any = None
    if settings.RAG_HYBRID_ENABLED:
        sparse_index = EpisodeBM25Index()
        hybrid_retriever = HybridRetriever(
            dense_retriever=_GraphRagDenseAdapter(rag_service),
            sparse_retriever=sparse_index,
            default_rrf_k=60,
            dense_weight=1.0,
            sparse_weight=1.0,
        )
        logger.info("ReflectiveRAGService: hybrid retrieval enabled (dense+BM25+RRF k=60)")

    query_reformulator: Any = None
    if settings.RAG_HYDE_MODE == "llm":
        query_reformulator = QueryReformulator(llm_adapter=llm_adapter)
        logger.info("ReflectiveRAGService: HyDE LLM mode enabled")

    service = ReflectiveRAGService(
        rag_service=rag_service,
        hybrid_retriever=hybrid_retriever,
        query_reformulator=query_reformulator,
    )
    return service
