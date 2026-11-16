"""Integration: UnifiedAuditor 集成テスト。

統合監査の出力形式を検証する。
これは削除された test_p2_architecture_ux_e2e.py の代替テスト。
"""

from __future__ import annotations

import pytest

from src.agents.specialists.unified_auditor import UnifiedAuditor


class _StubLLM:
    async def generate(self, prompt: str, temperature: float = 0.2) -> str:
        return (
            '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, '
            '"character_consistency": 85, "style_score": 85, "factual_score": 85, '
            '"structure_score": 85, "multimodal_score": 85, '
            '"strengths": ["良いフック"], "weaknesses": [], '
            '"actionable_patch": null, "summary": "合格水準"}'
        )

    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        return (
            '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, '
            '"character_consistency": 85, "style_score": 85, "factual_score": 85, '
            '"structure_score": 85, "multimodal_score": 85, '
            '"strengths": ["良いフック"], "weaknesses": [], '
            '"actionable_patch": null, "summary": "合格水準"}'
        )


@pytest.mark.asyncio
async def test_unified_auditor_output_format():
    """UnifiedAuditor.audit_qualitative の出力形式が QualitativeAudit であること。"""

    auditor = UnifiedAuditor(llm_gateway=_StubLLM())
    text = "王都の石畳を歩くアレンの前に、突如として黒装束の暗殺者が立ち塞がった。"

    qual = await auditor.audit_qualitative(
        text=text,
        character_profiles="アレン: 主人公、勇敢",
        plot_spec="暗殺者との遭遇",
    )

    # QualitativeAudit の必須フィールドを確認
    assert hasattr(qual, "overall_score")
    assert hasattr(qual, "hook_score")
    assert hasattr(qual, "emotional_score")
    assert hasattr(qual, "character_consistency")
    assert hasattr(qual, "critique")
    assert hasattr(qual, "actionable_patch")

    # スコア範囲チェック
    assert 0.0 <= qual.overall_score <= 100.0


@pytest.mark.asyncio
async def test_unified_auditor_quantitative_output():
    """UnifiedAuditor.audit_quantitative の出力形式を検証すること。"""

    auditor = UnifiedAuditor(llm_gateway=_StubLLM())
    text = "短い文。もう一つの短い文。対話もある。「こんにちは」と彼は言った。"

    score, meta = auditor.audit_quantitative(text)

    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0
    assert "rhythm_score" in meta
    assert "dialogue_ratio" in meta
    assert "cliches" in meta
    assert "cliffhanger_score" in meta
    assert isinstance(meta["cliches"], list)
