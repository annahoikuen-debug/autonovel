"""Integration: AuditAggregator メトリクステスト。

publish_aggregated_metrics の動作を検証する。
これは削除された test_phase2_full_flow.py の代替テスト。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.audit.aggregator import AuditAggregator, BookScoreResult


class _StubEventBus:
    """publish_async を記録するスタブイベントバス。"""

    def __init__(self) -> None:
        self.published: list[Any] = []

    async def publish_async(self, event: Any) -> None:
        self.published.append(event)


def _make_score_result(overall: float) -> BookScoreResult:
    return BookScoreResult(
        overall=overall,
        by_specialist={"consistency": overall, "creativity": overall, "reader_hook": overall,
                       "emotion_curve": overall, "style": overall, "factual": overall,
                       "structure": overall, "multimodal": overall},
        missing=[],
        weights_used={"consistency": 0.125, "creativity": 0.125, "reader_hook": 0.125,
                      "emotion_curve": 0.125, "style": 0.125, "factual": 0.125,
                      "structure": 0.125, "multimodal": 0.125},
        raw={},
    )


def _make_ctx(book_id: int = 1) -> dict[str, Any]:
    return {
        "book_id": book_id,
        "chapter_number": 2,
        "weight_variant": "default_v1",
        "genre": "fantasy",
        "phase": "writing",
        "correlation_id": "test-corr-123",
    }


@pytest.mark.asyncio
async def test_publish_aggregated_metrics_no_event_bus():
    """event_bus が None の場合、publish_aggregated_metrics は早期リターンすること。"""

    agg = AuditAggregator(
        specialists=[],
        weights={"consistency": 0.125, "creativity": 0.125, "reader_hook": 0.125, "emotion_curve": 0.125,
                 "style": 0.125, "factual": 0.125, "structure": 0.125, "multimodal": 0.125},
        event_bus=None,
    )

    # 例外が発生せず、正常に完了すること
    await agg.publish_aggregated_metrics(
        _make_score_result(85.0),
        _make_ctx(),
        min_pass_score=70.0,
    )


@pytest.mark.asyncio
async def test_publish_aggregated_metrics_publishes_event():
    """event_bus が設定されている場合、AgentEvent が publish されること。"""

    event_bus = _StubEventBus()
    agg = AuditAggregator(
        specialists=[],
        weights={"consistency": 0.125, "creativity": 0.125, "reader_hook": 0.125, "emotion_curve": 0.125,
                 "style": 0.125, "factual": 0.125, "structure": 0.125, "multimodal": 0.125},
        event_bus=event_bus,
    )

    await agg.publish_aggregated_metrics(
        _make_score_result(85.0),
        _make_ctx(),
        min_pass_score=70.0,
    )

    assert len(event_bus.published) == 1
    event = event_bus.published[0]
    assert event.agent == "audit.aggregated"
    assert event.payload["event"] == "audit.aggregated"
    assert event.payload["book_id"] == 1
    assert event.payload["overall_score"] == 85.0
    assert event.payload["regeneration_triggered"] is False  # 85 >= 70
    assert event.payload["lowest_dimension"] == "consistency"  # すべて同スコアなので最初のキー


@pytest.mark.asyncio
async def test_publish_aggregated_metrics_regeneration_triggered():
    """スコア未達の場合、regeneration_triggered=True となること。"""

    event_bus = _StubEventBus()
    agg = AuditAggregator(
        specialists=[],
        weights={"consistency": 0.125, "creativity": 0.125, "reader_hook": 0.125, "emotion_curve": 0.125,
                 "style": 0.125, "factual": 0.125, "structure": 0.125, "multimodal": 0.125},
        event_bus=event_bus,
    )

    await agg.publish_aggregated_metrics(
        _make_score_result(45.0),
        _make_ctx(),
        min_pass_score=70.0,
    )

    assert len(event_bus.published) == 1
    event = event_bus.published[0]
    assert event.payload["regeneration_triggered"] is True  # 45 < 70
