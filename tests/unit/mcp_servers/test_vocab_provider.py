"""Unit tests for SensoryVocabProvider."""

from __future__ import annotations

from src.mcp_servers.vocab_schemas import SensoryWord
from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider


def test_vocab_provider_empty():
    provider = SensoryVocabProvider()
    assert "Unsupported" in provider.read_resource("novel://vocab/invalid/path")
    assert "No vocabulary" in provider.read_resource("novel://vocab/sensory/unknown")
    assert len(provider.suggest_metaphors("test", "unknown")) == 0


def test_vocab_provider_registration_and_reading():
    provider = SensoryVocabProvider()
    words = [
        SensoryWord(
            word="冷たい鉄の感触", category="tactile", example_sentence="剣の柄が冷たく掌に食い込む。", nuance="tension"
        ),
        SensoryWord(
            word="血の鉄錆の匂い", category="olfactory", example_sentence="鼻腔を突く血の匂い。", nuance="danger"
        ),
    ]
    provider.register_words("fantasy", words)

    # Test resource read
    res_text = provider.read_resource("novel://vocab/sensory/fantasy")
    assert "FANTASY" in res_text
    assert "冷たい鉄の感触" in res_text
    assert "血の鉄錆の匂い" in res_text

    # Test metaphor suggestion
    sugs = provider.suggest_metaphors("血", "fantasy")
    assert len(sugs) == 1
    assert "血の鉄錆の匂い" in sugs[0]
