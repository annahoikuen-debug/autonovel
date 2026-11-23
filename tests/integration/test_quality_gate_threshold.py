"""Integration: 品質ゲート閾値テスト。

70 点合格ラインの挙動を検証する。
これは削除された test_p1_quality_enhancement_e2e.py の代替テスト。
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
        by_specialist={"structure": overall},
        missing=[],
        weights_used={"structure": 1.0},
        raw={},
    )


def _make_ctx() -> AgentContext:
    return AgentContext(
        book_id=10,
        branch_id=1,
        ep_num=2,
        artifacts={
            "drafted_text": "テスト用の原稿テキストです。",
            "world_bible_snapshot": {},
            "genre": "fantasy",
            "phase": "writing",
            "session": MagicMock(),
            "audit_retry_count": 0,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "expected_next_agent"),
    [
        (69.9, AgentName.WRITING),  # 合格ライン未満
        (70.0, AgentName.ILLUSTRATION),  # ちょうど合格ライン
        (70.1, AgentName.ILLUSTRATION),  # 合格ライン超過
        (100.0, AgentName.ILLUSTRATION),  # 満点
        (0.0, AgentName.WRITING),  # ゼロ点
    ],
)
async def test_quality_gate_threshold(score: float, expected_next_agent: AgentName):
    """品質ゲート閾値（70点）の境界値テスト。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx()

    result = node.to_agent_result(
        _make_score_result(score),
        ctx,
        min_pass_score=70.0,
    )

    assert result.next_agent == expected_next_agent, (
        f"score={score}: expected_next_agent={expected_next_agent} but got {result.next_agent}"
    )


@pytest.mark.asyncio
async def test_quality_gate_custom_threshold():
    """カスタム閾値（例：80点）でも正しく動作すること。"""

    node = AuditAggregatorNode(llm=_StubLLM())
    ctx = _make_ctx()

    # 75点は 80点閾値では不合格（WRITING へ）
    result = node.to_agent_result(
        _make_score_result(75.0),
        ctx,
        min_pass_score=80.0,
    )
    assert result.next_agent == AgentName.WRITING

    # 85点は 80点閾値では合格（ILLUSTRATION へ）
    result = node.to_agent_result(
        _make_score_result(85.0),
        ctx,
        min_pass_score=80.0,
    )
    assert result.next_agent == AgentName.ILLUSTRATION
