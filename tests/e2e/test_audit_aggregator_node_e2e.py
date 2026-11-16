"""E2E: AuditAggregatorNode の統合テスト。

監査→合格/差し戻し経路の E2E を検証する。
これは削除された test_pillar1_pipeline_e2e.py の代替テスト。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents.orchestrator import AgentContext, AgentName, AgentResult
from src.agents.specialists.adapter import AuditAggregatorNode
from src.engine.audit.aggregator import AuditAggregator, BookScoreResult


class _StubLLM:
    async def generate(self, prompt: str, temperature: float = 0.2) -> str:
        return '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, "character_consistency": 85, "style_score": 85, "factual_score": 85, "structure_score": 85, "multimodal_score": 85}'

    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        return '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, "character_consistency": 85, "style_score": 85, "factual_score": 85, "structure_score": 85, "multimodal_score": 85}'


def _make_score_result(overall: float, by_specialist: dict[str, float] | None = None) -> BookScoreResult:
    if by_specialist is None:
        by_specialist = {"structure": overall, "coherency": overall, "factual": overall}
    return BookScoreResult(
        overall=overall,
        by_specialist=by_specialist,
        missing=[],
        weights_used={},
        raw={},
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
async def test_audit_aggregator_node_pass_route():
    """スコアが合格ライン以上の場合、AgentResult が ILLUSTRATION を返すこと。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(MagicMock())

    result = node.to_agent_result(
        _make_score_result(85.0),
        ctx,
        min_pass_score=70.0,
    )

    assert isinstance(result, AgentResult)
    assert result.next_agent == AgentName.ILLUSTRATION


@pytest.mark.asyncio
async def test_audit_aggregator_node_reject_route():
    """スコアが合格ライン未満の場合、AgentResult が WRITING を返すこと。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(MagicMock())

    result = node.to_agent_result(
        _make_score_result(45.0),
        ctx,
        min_pass_score=70.0,
    )

    assert isinstance(result, AgentResult)
    assert result.next_agent == AgentName.WRITING
    assert result.should_retry is True
    assert result.is_backtrack is True


@pytest.mark.asyncio
async def test_audit_aggregator_node_retry_within_limit():
    """再試行回数が制限内の場合、差し戻し（WRITING）となること。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(MagicMock())
    ctx.artifacts["audit_retry_count"] = 1

    result = node.to_agent_result(
        _make_score_result(50.0),
        ctx,
        min_pass_score=70.0,
        max_retries=2,
    )

    assert result.next_agent == AgentName.WRITING


@pytest.mark.asyncio
async def test_audit_aggregator_node_exceeds_retry_limit():
    """再試行回数を超過した場合、ILLUSTRATION（合格扱い）へ進むこと。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(MagicMock())
    ctx.artifacts["audit_retry_count"] = 3

    result = node.to_agent_result(
        _make_score_result(50.0),
        ctx,
        min_pass_score=70.0,
        max_retries=2,
    )

    assert result.next_agent == AgentName.ILLUSTRATION


@pytest.mark.asyncio
async def test_audit_aggregator_degraded_all_missing():
    """全 specialist が missing の場合、overall=0.0 で不合格となること。"""

    agg = AuditAggregator(
        specialists=[],
        weights={"consistency": 0.125, "creativity": 0.125, "reader_hook": 0.125, "emotion_curve": 0.125,
                 "style": 0.125, "factual": 0.125, "structure": 0.125, "multimodal": 0.125},
    )
    result = agg.aggregate()

    assert result.overall == 0.0
