"""Sensory and Rhetoric Vocabulary Schemas and URI Parser."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any
import re


@dataclass
class SensoryWord:
    """感覚・レトリック語彙定義"""
    word: str
    category: str  # visual, auditory, olfactory, tactile, psychological
    example_sentence: str
    nuance: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenreVocabSet:
    """ジャンル別語彙セット"""
    genre: str
    words: List[SensoryWord] = field(default_factory=list)


def parse_vocab_uri(uri: str) -> Dict[str, Any]:
    """
    語彙リソースURIを解析する。
    対応URI:
      - novel://vocab/sensory/{genre}
    """
    match = re.match(r"^novel://vocab/sensory/([a-zA-Z0-9_-]+)$", uri)
    if match:
        genre = match.group(1)
        return {"type": "sensory_vocab", "genre": genre}

    return {"type": "unknown", "uri": uri}
