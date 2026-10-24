"""Tests for src/services/series_serializer.py."""

from __future__ import annotations

from src.easy_mode import EpisodeResult, SeriesResult
from src.services.series_serializer import episode_summary, series_to_dict


def test_episode_summary_basic():
    """episode_summary returns correct fields."""
    ep = EpisodeResult(
        episode_num=1,
        title="テスト話",
        content="テスト本文内容",
        word_count=100,
        audit_score=90.0,
        audit_passed=True,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
        needs_human_review=False,
    )
    d = episode_summary(ep)
    assert d["episode_num"] == 1
    assert d["title"] == "テスト話"
    assert d["word_count"] == 100
    assert d["audit_score"] == 90.0
    assert d["audit_passed"] is True
    assert d["rewrite_count"] == 0
    assert d["needs_human_review"] is False
    assert d["content_snippet"] == "テスト本文内容"


def test_series_to_dict_basic():
    """series_to_dict returns correct structure."""
    import datetime

    dt = datetime.datetime(2023, 1, 1, 0, 0, 0)
    ep = EpisodeResult(
        episode_num=1,
        title="第1話",
        content="本文",
        word_count=10,
        audit_score=80.0,
        audit_passed=True,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
        needs_human_review=False,
    )
    s = SeriesResult(
        genre="ファンタジー",
        title="テストシリーズ",
        concept="テストコンセプト",
        total_episodes=1,
        episodes=[ep],
        bible={"world": "test"},
        plot_outline=[{"step": 1}],
        metadata={"author": "tester"},
        status="completed",
        created_at=dt,
    )
    d = series_to_dict(s)
    assert d["genre"] == "ファンタジー"
    assert d["title"] == "テストシリーズ"
    assert d["concept"] == "テストコンセプト"
    assert d["total_episodes"] == 1
    assert d["status"] == "completed"
    assert d["created_at"] == "2023-01-01T00:00:00"
    assert len(d["episodes"]) == 1
    assert d["bible"] == {"world": "test"}
    assert d["plot_outline"] == [{"step": 1}]
    assert d["metadata"] == {"author": "tester"}


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
