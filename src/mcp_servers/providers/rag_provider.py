"""RAG and Memory Provider for MCP Server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RAGQueryRequest:
    """RAG検索リクエスト"""

    query: str
    top_k: int = 5
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RAGQueryResult:
    """RAG検索結果アイテム"""

    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RAGQueryResponse:
    """RAG検索レスポンス"""

    results: List[RAGQueryResult] = field(default_factory=list)
    summary: str = ""


class RAGMemoryProvider:
    """RAGおよびリフレクション記憶を管理・検索するプロバイダー"""

    def __init__(self) -> None:
        self.documents: List[Dict[str, Any]] = []

    def add_document(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """検索用ドキュメントを追加する"""
        self.documents.append({"content": content, "metadata": metadata or {}})

    def query(self, request: RAGQueryRequest) -> RAGQueryResponse:
        """キーワードマッチおよび簡易スコアリングに基づく検索を実行する"""
        query_terms = request.query.lower().split()
        scored_results: List[tuple[float, Dict[str, Any]]] = []

        for doc in self.documents:
            content = doc["content"]
            lower_content = content.lower()

            # マッチ度スコア計算
            matches = sum(1 for term in query_terms if term in lower_content)
            if matches > 0 or not query_terms:
                score = float(matches) / max(len(query_terms), 1)
                scored_results.append((score, doc))

        # スコア降順にソート
        scored_results.sort(key=lambda x: x[0], reverse=True)
        top_docs = scored_results[: request.top_k]

        results = [
            RAGQueryResult(content=doc["content"], score=score, metadata=doc["metadata"]) for score, doc in top_docs
        ]

        summary = "\n---\n".join([r.content for r in results])

        return RAGQueryResponse(results=results, summary=summary)
