"""src/services/narrative_scoring_service.py (NarrativeScoringService) の単体テスト."""

from __future__ import annotations

import pytest

from src.services.narrative_scoring_service import NarrativeScoringService


class TestNarrativeScoringService:
    """NarrativeScoringService のテスト."""

    @pytest.mark.asyncio
    async def test_score_empty_content(self):
        service = NarrativeScoringService(llm=None, prompt_manager=None)
        result = await service.score("")
        assert result == {"score": 0.0, "feedback": "Content is empty"}

    @pytest.mark.asyncio
    async def test_score_whitespace_content(self):
        # Whitespace のみは空ではないので、llm/prompt_manager None のフォールバックパス
        service = NarrativeScoringService(llm=None, prompt_manager=None)
        result = await service.score("   ")
        assert result["score"] == 75.0
        assert "Rule-based fallback" in result["feedback"]

    @pytest.mark.asyncio
    async def test_score_with_none_llm_and_prompt_manager(self):
        service = NarrativeScoringService(llm=None, prompt_manager=None)
        result = await service.score("本文のコンテンツです。")
        assert result["score"] == 75.0
        assert result["feedback"] == "Rule-based fallback evaluation: narrative structure is acceptable."
        assert "raw" not in result

    @pytest.mark.asyncio
    async def test_score_with_llm_but_none_prompt_manager(self):
        # llm はあるが prompt_manager が None の場合もフォールバック
        service = NarrativeScoringService(llm=object(), prompt_manager=None)
        result = await service.score("本文のコンテンツです。")
        assert result["score"] == 75.0

    @pytest.mark.asyncio
    async def test_score_with_llm_exception_fallback(self):
        # llm.generate_json が例外を投げる場合、フォールバックスコア 70.0
        class FailingLLM:
            async def generate_json(self, purpose, prompt):
                raise RuntimeError("LLM call failed")

        class FailingPromptManager:
            def build_critique_quality_prompt(self, book_title, summary_data_json):
                return "prompt"

        service = NarrativeScoringService(llm=FailingLLM(), prompt_manager=FailingPromptManager())
        result = await service.score("本文のコンテンツです。")
        assert result["score"] == 70.0
        assert "Fallback due to error" in result["feedback"]

    @pytest.mark.asyncio
    async def test_score_llm_returns_dict_with_metadata(self):
        class GoodLLM:
            async def generate_json(self, purpose, prompt):
                return {"metadata": {"score": 88.5, "feedback": "良い構造です"}}

        class GoodPromptManager:
            def build_critique_quality_prompt(self, book_title, summary_data_json):
                return "prompt"

        service = NarrativeScoringService(llm=GoodLLM(), prompt_manager=GoodPromptManager())
        result = await service.score("本文のコンテンツです。")
        assert result["score"] == 88.5
        assert result["feedback"] == "良い構造です"
        assert result["raw"] == {"metadata": {"score": 88.5, "feedback": "良い構造です"}}

    @pytest.mark.asyncio
    async def test_score_llm_returns_non_dict(self):
        class NonDictLLM:
            async def generate_json(self, purpose, prompt):
                return "not a dict"

        class GoodPromptManager:
            def build_critique_quality_prompt(self, book_title, summary_data_json):
                return "prompt"

        service = NarrativeScoringService(llm=NonDictLLM(), prompt_manager=GoodPromptManager())
        result = await service.score("本文のコンテンツです。")
        # result が dict ではないので score_val = 75.0
        assert result["score"] == 75.0
