"""Lore Provider for managing characters and world bible data."""
from __future__ import annotations

from typing import Dict, List, Optional
from src.mcp_servers.schemas import (
    CharacterProfile,
    WorldBibleSection,
    LoreQueryRequest,
    LoreQueryResponse,
)


class LoreProvider:
    """世界観およびキャラクター設定を管理し、オンデマンドで抽出・提供するプロバイダー"""

    def __init__(self) -> None:
        self.characters: Dict[str, CharacterProfile] = {}
        self.bible_sections: Dict[str, WorldBibleSection] = {}

    def register_character(self, profile: CharacterProfile) -> None:
        """キャラクタープロファイルを登録する"""
        self.characters[profile.name] = profile
        for alias in profile.aliases:
            self.characters[alias] = profile

    def register_bible_section(self, section: WorldBibleSection) -> None:
        """世界観セクションを登録する"""
        self.bible_sections[section.section_id] = section

    def get_character(self, name: str) -> Optional[CharacterProfile]:
        """キャラクター名またはエイリアスからプロファイルを取得する"""
        return self.characters.get(name)

    def get_bible_section(self, section_id: str) -> Optional[WorldBibleSection]:
        """世界観セクションを取得する"""
        return self.bible_sections.get(section_id)

    def query(self, request: LoreQueryRequest) -> LoreQueryResponse:
        """リクエストに基づき、関連するキャラクターと世界観セクションを抽出して返す"""
        matched_chars: List[CharacterProfile] = []
        seen_chars = set()

        # 指定されたキャラクター名、またはクエリに含まれるキャラクターを検索
        for name, profile in self.characters.items():
            if profile.name in seen_chars:
                continue
            if name in request.character_names or any(c_name in request.query for c_name in [profile.name] + profile.aliases):
                matched_chars.append(profile)
                seen_chars.add(profile.name)

        matched_sections: List[WorldBibleSection] = []
        for sec_id, section in self.bible_sections.items():
            if sec_id in request.tags or any(tag in request.query for tag in section.tags) or section.title in request.query:
                matched_sections.append(section)

        # 要約の構築（トークン圧縮用）
        summary_parts = []
        for char in matched_chars:
            summary_parts.append(f"Char [{char.name}]: {char.personality}, {char.speech_pattern}")
        for sec in matched_sections:
            summary_parts.append(f"Bible [{sec.title}]: {sec.content[:200]}...")

        compressed_summary = "\n".join(summary_parts)

        return LoreQueryResponse(
            characters=matched_chars,
            bible_sections=matched_sections,
            compressed_summary=compressed_summary,
        )
