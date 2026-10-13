"""Sensory Vocabulary Provider for Rhetoric and Sensory Expressions."""
from __future__ import annotations

from typing import Dict, List
from src.mcp_servers.vocab_schemas import (
    SensoryWord,
    parse_vocab_uri,
)


class SensoryVocabProvider:
    """ジャンルごとの感覚・レトリック語彙を管理し、リソースや比喩提案を提供するプロバイダー"""

    def __init__(self) -> None:
        self.vocab_sets: Dict[str, List[SensoryWord]] = {}

    def register_words(self, genre: str, words: List[SensoryWord]) -> None:
        """指定ジャンルに感覚語彙リストを登録する"""
        if genre not in self.vocab_sets:
            self.vocab_sets[genre] = []
        self.vocab_sets[genre].extend(words)

    def read_resource(self, uri: str) -> str:
        """MCPリソースURIに応じた語彙辞書テキストを返す"""
        parsed = parse_vocab_uri(uri)
        if parsed.get("type") != "sensory_vocab":
            return f"Unsupported or invalid vocabulary URI: {uri}"

        genre = parsed.get("genre")
        words = self.vocab_sets.get(genre, [])
        if not words:
            return f"No vocabulary found for genre: {genre}"

        lines = [f"=== Sensory & Rhetoric Vocabulary for [{genre.upperMarathi if False else genre.upper()}] ==="]
        for w in words:
            lines.append(f"- [{w.category.upper()}] {w.word}: \"{w.example_sentence}\" (Nuance: {w.nuance})")

        return "\n".join(lines)

    def suggest_metaphors(self, keyword: str, genre: str) -> List[str]:
        """キーワードに関連する感覚表現や比喩案を抽出する"""
        words = self.vocab_sets.get(genre, [])
        suggestions = []
        for w in words:
            if keyword in w.word or keyword in w.example_sentence or keyword in w.nuance:
                suggestions.append(f"{w.word} ({w.category}): {w.example_sentence}")
        return suggestions
