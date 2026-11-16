"""E2E: UnifiedAuditor の degraded（LLM 未設定）経路テスト。

LLM 未設定の場合、品質ゲートは「評価不能＝不合格」として
fail-closed（WRITING に戻す）動作をすることを検証する。
これは削除された test_pillar1_fault_tolerance.py の代替テスト。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.specialists.unified_auditor import UnifiedAuditor


class _NoLLM:
    """LLM を持たないダミーゲートウェイ。"""


@pytest.mark.asyncio
async def test_unified_auditor_degraded_llm_none_fail_closed():
    """LLM 未設定（degraded）の場合、audit_qualitative は degraded=True を返すこと。

    品質ゲートはこれを不合格として扱い、WRITING に戻す必要がある。
    """
    auditor = UnifiedAuditor(llm_gateway=None)
    text = "王都の石畳を歩くアレンの前に、突如として黒装束の暗殺者が立ち塞がった。"

    quant_score, quant_meta = auditor.audit_quantitative(text)
    qual, degraded = await auditor._audit_qualitative_with_status(text)

    assert degraded is True, "LLM 未設定の場合は degraded=True であるべき"
    assert qual.overall_score == 0.0, "degraded のスコアはプレースホルダ（0点）であるべき"
    assert isinstance(quant_score, float)
    assert "rhythm_score" in quant_meta


@pytest.mark.asyncio
async def test_unified_auditor_degraded_invalid_llm_fail_closed():
    """generate / generate_text を持たない LLM オブジェクトでも degrade すること。

    無効な LLM が渡された場合、_call_llm が AttributeError を出し、
    audit_qualitative は degraded=True を返す。
    """
    auditor = UnifiedAuditor(llm_gateway=_NoLLM())
    text = "テスト用の原稿テキストです。"

    qual, degraded = await auditor._audit_qualitative_with_status(text)

    assert degraded is True, "無効な LLM の場合は degraded=True であるべき"
    assert qual.overall_score == 0.0
