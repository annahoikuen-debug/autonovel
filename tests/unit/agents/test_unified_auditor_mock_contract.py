"""Unit tests verifying UnifiedAuditor qualitative & quantitative contracts with mock LLM."""

import pytest

from src.agents.specialists.unified_auditor import UnifiedAuditor


class MockLowConsistencyLLM:
    """Mock LLM that simulates an audit response with low consistency."""

    async def generate(self, prompt: str, temperature: float = 0.2) -> str:
        return (
            '{"hook_score": 52.0, "emotional_score": 58.0, '
            '"character_consistency": 45.0, "overall_score": 55.0, '
            '"critique": "Inconsistency detected in character death status", '
            '"actionable_patch": null}'
        )

    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        return await self.generate(prompt, temperature)


@pytest.mark.asyncio
async def test_unified_auditor_mock_contract_scoring():
    """UnifiedAuditor correctly parses and maps qualitative scores."""
    unified = UnifiedAuditor(llm_gateway=MockLowConsistencyLLM())
    text = "昨日の戦いで死んだはずの仲間が朝ごはんを食べていた。今日はいい天気だ。"

    quant_score, quant_meta = unified.audit_quantitative(text)
    assert isinstance(quant_score, float)
    assert isinstance(quant_meta, dict)

    qual = await unified.audit_qualitative(text)
    assert qual.hook_score == 52.0
    assert qual.emotional_score == 58.0
    assert qual.character_consistency == 45.0
    assert qual.overall_score == 55.0
    assert "Inconsistency detected" in qual.critique

    report = await unified.audit(text)
    assert report.qualitative.character_consistency == 45.0
    assert report.final_score > 0
