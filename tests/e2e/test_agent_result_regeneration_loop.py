"""E2E: to_agent_result の再生成ループテスト。

差し戻し→再生成→合格のフローを検証する。
これは削除された test_regeneration_loop_e2e.py の代替テスト。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents.orchestrator import AgentContext, AgentName
from src.agents.specialists.adapter import AuditAggregatorNode
from src.engine.audit.aggregator import BookScoreResult


class _StubLLM:
    async def generate(self, prompt: str, temperature: float = 0.2) -> str:
        return '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, "character_consistency": 85, "style_score": 85, "factual_score": 85, "structure_score": 85, "multimodal_score": 85}'

    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        return '{"overall_score": 85, "hook_score": 85, "emotional_score": 85, "character_consistency": 85, "style_score": 85, "factual_score": 85, "structure_score": 85, "multimodal_score": 85}'


def _make_score_result(overall: float) -> BookScoreResult:
    return BookScoreResult(
        overall=overall,
        by_specialist={"structure": overall, "coherency": overall, "factual": overall},
        missing=[],
        weights_used={},
        raw={},
    )


def _make_ctx(retry_count: int = 0) -> AgentContext:
    return AgentContext(
        book_id=10,
        branch_id=1,
        ep_num=2,
        artifacts={
            "drafted_text": "テスト用の原稿テキストです。",
            "world_bible_snapshot": {"characters": [], "locations": []},
            "genre": "fantasy",
            "phase": "writing",
            "session": MagicMock(),
            "audit_retry_count": retry_count,
        },
    )


@pytest.mark.asyncio
async def test_regeneration_loop_first_rejection():
    """1回目の差し戻し：スコア未達 → WRITING へ戻ること。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(retry_count=0)

    result = node.to_agent_result(
        _make_score_result(45.0),
        ctx,
        min_pass_score=70.0,
        max_retries=3,
    )

    assert result.next_agent == AgentName.WRITING
    assert result.should_retry is True
    assert result.is_backtrack is True


@pytest.mark.asyncio
async def test_regeneration_loop_second_attempt_pass():
    """2回目（再試行1回目）：スコア達成 → 合格（ILLUSTRATION へ）こと。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(retry_count=1)

    result = node.to_agent_result(
        _make_score_result(75.0),
        ctx,
        min_pass_score=70.0,
        max_retries=3,
    )

    assert result.next_agent == AgentName.ILLUSTRATION


@pytest.mark.asyncio
async def test_regeneration_loop_exhausted_retries():
    """再試行回数を使い果たした場合：ILLUSTRATION へ進むこと（max_retries 超過）。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(retry_count=5)

    result = node.to_agent_result(
        _make_score_result(40.0),
        ctx,
        min_pass_score=70.0,
        max_retries=3,
    )

    assert result.next_agent == AgentName.ILLUSTRATION


@pytest.mark.asyncio
async def test_regeneration_loop_actionable_guidance():
    """不合格時、最低スコア次元に基づくガイダンスが含まれること。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx(retry_count=0)

    result = node.to_agent_result(
        _make_score_result(45.0),
        ctx,
        min_pass_score=70.0,
        max_retries=3,
    )

    assert result.next_agent == AgentName.WRITING
    assert "regeneration_directive" in result.artifacts
    assert result.artifacts["audit_status"] == "rejected"
