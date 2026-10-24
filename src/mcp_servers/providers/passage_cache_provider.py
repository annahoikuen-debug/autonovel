"""Passage Cache Provider for Semantic Prompt Caching and Similar Scene Search."""

from __future__ import annotations

from typing import Dict, List
from src.mcp_servers.passage_cache_schemas import (
    CachedPassage,
    PassageSearchRequest,
    PassageSearchResponse,
)


class PassageCacheProvider:
    """シーン描写のセマンティックキャッシュおよび類似パッセージ検索を管理するプロバイダー"""

    def __init__(self) -> None:
        self.passages: Dict[str, CachedPassage] = {}

    def register_passage(self, passage: CachedPassage) -> None:
        """パッセージをキャッシュに登録する"""
        self.passages[passage.passage_id] = passage

    def search_similar_passages(self, request: PassageSearchRequest) -> PassageSearchResponse:
        """クエリやタグに一致する類似パッセージを検索し、スコアリングして上位を返す"""
        query_terms = request.query.lower().split()
        scored_results: List[tuple[float, CachedPassage]] = []

        for passage in self.passages.values():
            # タグフィルタ
            if request.tags and not any(tag in passage.tags for tag in request.tags):
                continue

            target_text = f"{passage.intent} {passage.body}".lower()
            matches = sum(1 for term in query_terms if term in target_text)

            if matches > 0 or not query_terms:
                score = float(matches) / max(len(query_terms), 1)
                scored_results.append((score, passage))

        # スコア降順にソート
        scored_results.sort(key=lambda x: x[0], reverse=True)
        top_items = scored_results[: request.top_k]

        matched_passages: List[CachedPassage] = []
        for score, p in top_items:
            # ヒットカウントをインクリメント
            p.hit_count += 1
            matched_passages.append(p)

        summary_parts = [f"Found {len(matched_passages)} similar passages for query: '{request.query}'"]
        for p in matched_passages:
            summary_parts.append(
                f"- [{p.passage_id}] Intent: {p.intent} (Hits: {p.hit_count})\n  Body: {p.body[:100]}..."
            )

        return PassageSearchResponse(
            passages=matched_passages,
            search_summary="\n".join(summary_parts),
        )
