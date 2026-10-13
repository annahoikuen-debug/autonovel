"""Unit tests for vocabulary schemas and URI parser."""
from __future__ import annotations

from src.mcp_servers.vocab_schemas import (
    SensoryWord,
    GenreVocabSet,
    parse_vocab_uri,
)


def test_parse_vocab_uri_valid():
    res = parse_vocab_uri("novel://vocab/sensory/fantasy")
    assert res["type"] == "sensory_vocab"
    assert res["genre"] == "fantasy"


def test_parse_vocab_uri_invalid():
    res = parse_vocab_uri("novel://vocab/invalid/path")
    assert res["type"] == "unknown"


def test_vocab_schemas_instantiation():
    word = SensoryWord(
        word="泥の匂い",
        category="olfactory",
        example_sentence="雨上がりの湿った泥の匂いが鼻をついた。",
        nuance="gloomy"
    )
    assert word.category == "olfactory"

    vocab_set = GenreVocabSet(genre="fantasy", words=[word])
    assert vocab_set.genre == "fantasy"
    assert len(vocab_set.words) == 1
