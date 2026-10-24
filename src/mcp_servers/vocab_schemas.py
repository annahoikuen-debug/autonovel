"""Sensory and Rhetoric Vocabulary Schemas and URI Parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any
import re


@dataclass
class SensoryWord:
    """感覚・レトリック語彙定義"""

    word: str
    category: str  # visual, auditory, olfactory, tactile, psychological, metaphor, onomatopoeia
    example_sentence: str
    nuance: str = ""
    intensity: float = 0.5  # 0.0 (穏やか/日常) 〜 1.0 (極限/熱狂)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SampledVocabResult:
    """情動強度サンプリング結果"""

    category: str
    target_intensity: float
    items: List[Dict[str, Any]]
    count: int
    genre: str = "general"


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
