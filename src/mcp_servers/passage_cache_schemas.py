"""Passage Cache Schemas for Semantic Prompt Caching and Similar Scene Search."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class CachedPassage:
    """キャッシュされたシーンパッセージ定義"""

    passage_id: str
    intent: str
    body: str
    tags: List[str] = field(default_factory=list)
    hit_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PassageSearchRequest:
    """類似パッセージ検索リクエスト"""

    query: str
    top_k: int = 3
    tags: List[str] = field(default_factory=list)


@dataclass
class PassageSearchResponse:
    """類似パッセージ検索レスポンス"""

    passages: List[CachedPassage] = field(default_factory=list)
    search_summary: str = ""
