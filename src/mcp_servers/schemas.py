"""Lore/Bible MCP Server Schemas and Data Classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class CharacterProfile:
    """キャラクタープロファイル定義"""

    name: str
    aliases: List[str] = field(default_factory=list)
    role: str = ""
    appearance: str = ""
    personality: str = ""
    speech_pattern: str = ""
    secrets_and_flaws: str = ""
    relationships: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldBibleSection:
    """世界観セクション定義"""

    section_id: str
    title: str
    content: str
    tags: List[str] = field(default_factory=list)


@dataclass
class LoreQueryRequest:
    """Lore検索リクエスト"""

    query: str
    character_names: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    max_tokens: int = 1000


@dataclass
class LoreQueryResponse:
    """Lore検索レスポンス"""

    characters: List[CharacterProfile] = field(default_factory=list)
    bible_sections: List[WorldBibleSection] = field(default_factory=list)
    compressed_summary: str = ""
