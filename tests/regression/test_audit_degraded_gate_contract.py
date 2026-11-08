"""Audit degraded ゲートの契約テスト.

LLM 未設定（degraded=True）は「評価不能＝不合格」という
正当な防御（src/agents/specialists/unified_auditor.py:31,50）であるため、
未設定のときは ILLUSTRATION に進まず WRITING に戻されること、
スタブ LLM を渡せば正常系（ILLUSTRATION）に進むことの
両方向を検証する。これによりゲートが「常に止まる」「常に通る」
どちらの過剰修正でも赤くなる。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents.orchestrator import AgentContext, AgentName
from src.agents.specialists.adapter import AuditAggregatorNode


class _StubLLM:
    async def generate(self, prompt: str, temperature: float = 0.2) -> str:
        return (
            '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, '
            '"character_consistency": 85, "style_score": 85, "factual_score": 85, '
            '"structure_score": 85, "multimodal_score": 85}'
        )

    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        return (
            '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, '
            '"character_consistency": 85, "style_score": 85, "factual_score": 85, '
            '"structure_score": 85, "multimodal_score": 85}'
        )


def _make_ctx(mock_session: MagicMock) -> AgentContext:
    return AgentContext(
        book_id=10,
        branch_id=1,
        ep_num=2,
        artifacts={
            "drafted_text": (
                "王都の石畳を歩くアレンの前に、突如として黒装束の暗殺者が立ち塞がった。"
                "「ここで死んでもらう」と暗殺者が呟いたが、アレンは剣を抜き構えた。"
            ),
            "world_bible_snapshot": {
                "characters": [{"name": "アレン"}, {"name": "暗殺者"}],
                "locations": ["王都"],
            },
            "genre": "fantasy",
            "phase": "writing",
            "session": mock_session,
        },
    )


@pytest.mark.asyncio
async def test_degraded_llm_none_routes_back_to_writing() -> None:
    """LLM 未設定（degraded）のとき、品質ゲートが不合格として
    ILLUSTRATION に進まず WRITING に戻すこと（ゲートが機能している証拠）."""
    mock_session = MagicMock()
    node = AuditAggregatorNode(repo=MagicMock(), llm=None)
    result = await node(_make_ctx(mock_session))
    assert result.next_agent == AgentName.WRITING
    assert result.error is None


@pytest.mark.asyncio
async def test_stub_llm_routes_to_illustration() -> None:
    """スタブ LLM を渡せば degraded にならず、正常系として
    ILLUSTRATION に進むこと（ゲートが「常に止まる」過剰修正でないこと）."""
    mock_session = MagicMock()
    node = AuditAggregatorNode(repo=MagicMock(), llm=_StubLLM())
    result = await node(_make_ctx(mock_session))
    assert result.next_agent == AgentName.ILLUSTRATION
    assert result.error is None
