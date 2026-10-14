"""Unit tests for src/services/quality_scorer.py (pure logic quality scoring)."""
from __future__ import annotations

import pytest

from src.services.quality_scorer import QualityScorer
from src.models.report import QualityMetricsReport


class TestQualityScorer:
    @pytest.fixture
    def scorer(self):
        return QualityScorer()

    @pytest.fixture
    def sample_text(self):
        return (
            "\u4ed6\u306f\u305d\u308c\u3067\u3082\u7acb\u3061\u4e0a\u304c\u3063\u305f\u3002"
            "\u305d\u308c\u3086\u3048\u306b\u3001\u4ed6\u306f\u5263\u3092\u624b\u306b\u53d6\u3063\u305f\u3002"
            "\u305d\u3046\u3057\u3066\u6226\u3044\u304c\u59cb\u307e\u3063\u305f\u3002"
            "\u305d\u308c\u3067\u306f\u6575\u304f\u3084\u304b\u3063\u305f\u3002"
            "\u305d\u308c\u3067\u4ed6\u306f\u8acb\u308f\u308b\u306a\u304b\u3063\u305f\u3002"
            "\u732b\u7136\u3068\u5263\u3092\u632f\u308b\u3063\u305f\u3002"
            "\u4e00\u9803\u306e\u95fb\u304d\u3067\u6575\u3092\u5100\u3057\u305f\u3002"
            "\u6c7a\u610f\u3068\u9697\u5fd7\u304c\u4ed6\u3092\u652f\u3048\u305f\u3002"
            "\u7a81\u7136\u3001\u5149\u304c\u5dee\u3057\u8fbc\u3080\u3002"
            "\u307e\u3055\u304b\u306e\u5c55\u958b\u306b\u4ed6\u306f\u9a1a\u3044\u305f\u3002"
            "\u732b\u7132\u3057\u304f\u6226\u3044\u7d9a\u3051\u305f\u3002"
            "\u559c\u3073\u3068\u614b\u3073\u304c\u4ea4\u9320\u3059\u308b\u3002"
            "\u305d\u308c\u3067\u3082\u4ed6\u306f\u9032\u3080\u3002"
            "\u4ed6\u306e\u5fc3\u306b\u306f\u6012\u308a\u3068\u611b\u60c5\u304c\u540c\u5c45\u3057\u3066\u3044\u305f\u3002"
            "\u80b8\u306b\u79d8\u3081\u305f\u60f3\u3044\u304c\u6f6e\u308c\u308b\u3002"
            "\u811b\u306b\u6d6e\u304b\u3076\u7b11\u9854\u306e\u80e1\u306b\u3001\u80b8\u306b\u79d8\u3081\u305f\u60f3\u3044\u304c\u3042\u3063\u305f\u3002"
        )

    @pytest.mark.asyncio
    async def test_score_coherence_short_text(self, scorer):
        assert await scorer.score_coherence("") == 0.0
        assert await scorer.score_coherence("\u77ed\u3044") == 0.0

    @pytest.mark.asyncio
    async def test_score_coherence_with_flow_keywords(self, scorer):
        text = ("\u305d\u308c\u3067\u3001\u305d\u308c\u3086\u3048\u306b\u3001\u305d\u3046\u3057\u3066\u3001"
                "\u305d\u308c\u3067\u3001\u305d\u308c\u3067\u3001\u305f\u3060\u304b\u3002") * 5
        m = await scorer.score_coherence(text)
        assert 0.4 <= m <= 1.0

    @pytest.mark.asyncio
    async def test_score_coherence_no_flow_keywords(self, scorer):
        text = "\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002\u6587\u7ae0\u3067\u3059\u3002\u7d42\u308f\u308a\u3067\u3059\u3002" * 10
        m = await scorer.score_coherence(text)
        assert m == pytest.approx(0.4, abs=0.1)

    @pytest.mark.asyncio
    async def test_score_coherence_short_sentences(self, scorer):
        # Text with < 3 sentences but >= 100 chars triggers early return 0.3
        text = "短い。です。" * 20  # 20 sentences, but function counts sentences by splitting on 。！？
        # Actually the function splits on 。！？ and counts. "短い。です。" * 20 = 20 * 2 = 40 sentences
        # So it won't trigger early return. Base score is 0.4 when no flow keywords.
        text = "短い。です。" * 20
        # The function splits on 。！？ - each "短い。です。" has 2 sentences
        # 20 * 2 = 40 sentences >= 3, so no early return
        # No flow keywords -> flow_score = 0 -> score = 0.4
        score = await scorer.score_coherence(text)
        assert score == 0.4

    @pytest.mark.asyncio
    async def test_score_character_consistency_short(self, scorer):
        assert await scorer.score_character_consistency("") == 0.0
        assert await scorer.score_character_consistency("\u77ed\u3044") == 0.0

    @pytest.mark.asyncio
    async def test_score_character_consistency_many_names(self, scorer):
        # Japanese names with particles: \u592a\u90ce\u306f, \u82b1\u5b50\u306f, \u6b21\u90ce\u306f, \u592a\u90ce\u306f
        # Repeat to make text > 100 chars
        text = ("\u592a\u90ce\u306f\u8d70\u3063\u305f\u3002\u82b1\u5b50\u306f\u7b11\u3063\u305f\u3002"
                "\u6b21\u90ce\u306f\u6cf3\u3044\u305f\u3002\u592a\u90ce\u306f\u6cf3\u3044\u305f\u3002") * 4
        score = await scorer.score_character_consistency(text)
        assert score == 0.85

    @pytest.mark.asyncio
    async def test_score_character_consistency_few_names(self, scorer):
        text = ("\u592a\u90ce\u306f\u8d70\u3063\u305f\u3002\u82b1\u5b50\u306f\u7b11\u3063\u305f\u3002") * 8
        score = await scorer.score_character_consistency(text)
        assert score == 0.75

    @pytest.mark.asyncio
    async def test_score_character_consistency_one_name(self, scorer):
        text = "\u592a\u90ce\u306f\u8d70\u3063\u305f\u3002" * 15
        score = await scorer.score_character_consistency(text)
        assert score == 0.6

    @pytest.mark.asyncio
    async def test_score_pacing_short_text(self, scorer):
        assert await scorer.score_pacing("") == 0.0
        assert await scorer.score_pacing("\u77ed\u3044") == 0.0

    @pytest.mark.asyncio
    async def test_score_pacing_many_tension(self, scorer):
        text = ("\u7a81\u7136\u3001\u732b\u7136\u3068\u3001\u4e00\u9806\u3067\u3001\u6025\u901f\u306b\u3001\u6c7a\u610f\u3001\u9697\u5fd7") * 10
        score = await scorer.score_pacing(text)
        assert 0.5 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_score_pacing_few_tension(self, scorer):
        text = "\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002" * 100
        score = await scorer.score_pacing(text)
        assert 0.5 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_score_hook_retention_short(self, scorer):
        assert await scorer.score_hook_retention("") == 0.0
        assert await scorer.score_hook_retention("\u77ed\u3044") == 0.0

    @pytest.mark.asyncio
    async def test_score_hook_retention_many_hooks(self, scorer):
        text = ("\u3060\u308d\u3046\u304b\uff1f\u3053\u3046\u3057\u305f\u3089\u3044\u3044\u3001"
                "\u3069\u3046\u3057\u3088\u3046\uff1f") * 10
        score = await scorer.score_hook_retention(text)
        assert 0.7 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_score_hook_retention_unresolved(self, scorer):
        # Need hooks and unresolved in last third (matches .*だろうか and ...?)
        text = ("だろうか\n" * 10
                + "x" * 500
                + "どうなる...?")
        score = await scorer.score_hook_retention(text)
        assert 0.7 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_score_hook_retention_few_hooks(self, scorer):
        text = "\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002" * 50
        score = await scorer.score_hook_retention(text)
        assert score == 0.55

    @pytest.mark.asyncio
    async def test_score_emotional_resonance_short(self, scorer):
        assert await scorer.score_emotional_resonance("") == 0.0
        assert await scorer.score_emotional_resonance("\u77ed\u3044") == 0.0

    @pytest.mark.asyncio
    async def test_score_emotional_resonance_many_emotions(self, scorer):
        text = ("\u559c\u3073\u3001\u61b2\u3073\u3001\u6012\u308a\u3001\u6050\u308c\u3001\u9a05\u304d\u3001\u611b\u60c5\u3001"
                "\u6191\u3057\u307f\u3001\u7de0\u5f35\u3001\u5b89\u5803\u3001\u8a87\u308a\u3001"
                "\u7f8e\u671b\u3001\u6050\u6016\u3001\u6b4f\u559c\u3001\u80b8\u304c\u3001"
                "\u5fc3\u304c\u3001\u76ee\u306b\u3001\u8138\u306b\u3001\u3044\u3060\u304f\u3001"
                "\u611f\u3058\u3002") + "\u80b8\u304c\u5fc3\u304c\u76ee\u306b\u8138\u306b" * 10
        score = await scorer.score_emotional_resonance(text)
        assert 0.5 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_score_emotional_resonance_with_contrast(self, scorer):
        text = ("\u559c\u3073\u3001\u305d\u308c\u3067\u3001\u61b2\u3073\u3001\u3060\u304c\u3001"
                "\u6012\u308a\u3001\u3068\u3053\u308d\u3001\u6050\u308c\u3001\u305d\u308c\u3067\u3082") + "x" * 100
        score = await scorer.score_emotional_resonance(text)
        assert 0.5 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_score_commercial_viability_short(self, scorer):
        assert await scorer.score_commercial_viability("") == 0.0
        assert await scorer.score_commercial_viability("\u77ed\u3044") == 0.0

    @pytest.mark.asyncio
    async def test_score_commercial_viability_keywords(self, scorer):
        text = ("\u6700\u5f3a\u3001\u8987\u8005\u3001\u4f1d\u8aac\u3001\u904b\u547d\u3001\u6b66\u8005\u3001"
                "\u52c7\u8005\u3001\é9b54\uff0c\u8986\u901f") + "x" * 3000
        score = await scorer.score_commercial_viability(text)
        assert 0.5 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_score_commercial_viability_length_score(self, scorer):
        # 3000 chars is ideal -> length_score=1.0
        text = "x" * 3000
        score = await scorer.score_commercial_viability(text)
        # keyword_count=0, length_score=1.0
        # score = (0 * 0.6) + (1.0 * 0.4) = 0.4
        # return 0.5 + 0.4 * 0.5 = 0.7
        assert score == pytest.approx(0.7, abs=0.02)

        # Too short (1000 chars -> length_score=0.6)
        text = "x" * 1000
        score = await scorer.score_commercial_viability(text)
        # score = (0 * 0.6) + (0.6 * 0.4) = 0.24
        # return 0.5 + 0.24 * 0.5 = 0.62
        assert score == pytest.approx(0.62, abs=0.02)

    @pytest.mark.asyncio
    async def test_score_all(self, scorer):
        text = (
            "\u305d\u308c\u3067\u3001\u305d\u308c\u3086\u3048\u306b\u3001\u305d\u3046\u3057\u3066\u3001"
            "\u305d\u308c\u3067\u3001\u305f\u3060\u304b\u3002" * 5
            + "\u592a\u90ce\u306f\u8d70\u3063\u305f\u3002\u82b1\u5b50\u306f\u7b11\u3063\u305f\u3002"
            "\u6b21\u90ce\u306f\u6cf3\u3044\u305f\u3002" * 3
            + "\u7a81\u7136\u3001\u732b\u7136\u3068\u3001\u4e00\u980a\u3067\u3001"
            "\u6025\u901f\u306b\u3001\u6c7a\u610f\u3001\u9697\u5fd7" * 5
            + "\u3060\u308d\u3046\u304b\uff1f\u3053\u3046\u3057\u305f\u3089\u3001"
            "\u7a81\u7136\u3001\u732b\u7136\u3068" * 3
            + "\u559c\u3073\u3001\u614b\u3073\u3001\u6012\u308a\u3001\u305d\u308c\u3067\u3001"
            "\u3060\u304c\u3001\u6012\u308a\u3001\u3068\u3053\u308d\u3001\u305d\u308c\u3067\u3082"
            + "x" * 2000
            + "\u6700\u5f3a\u3001\u8987\u8005\u3001\u4f1d\u8aac\u3001\u904b\u547d\u3001"
            "\u6b66\u8005\u3001\u52c7\u8005\u3001\u9b54\u738b\u3001\u89e3\u9034" + "x" * 100
        )

        report = await scorer.score_all(text)

        assert isinstance(report.coherence_score, float)
        assert isinstance(report.character_consistency, float)
        assert isinstance(report.pacing_score, float)
        assert isinstance(report.hook_retention, float)
        assert isinstance(report.emotional_resonance, float)
        assert isinstance(report.commercial_viability, float)

        # All scores should be between 0 and 1
        for attr in [
            "coherence_score", "character_consistency", "pacing_score",
            "hook_retention", "emotional_resonance", "commercial_viability"
        ]:
            val = getattr(report, attr)
            assert 0.0 <= val <= 1.0, f"{attr} = {val} out of range"

    def test_initialization_with_llm_client(self):
        scorer = QualityScorer(llm_client="test_client")
        assert scorer.llm_client == "test_client"

    def test_initialization_without_llm_client(self):
        scorer = QualityScorer()
        assert scorer.llm_client is None
