"""Additional tests for src/services/series_serializer.py."""
from __future__ import annotations

from src.easy_mode import EpisodeResult, SeriesResult
from src.easy_mode.spice_guard import SpiceElement
from src.services.series_serializer import episode_summary, series_to_dict


def test_episode_summary_empty_content():
    """episode_summary handles empty content."""
    ep = EpisodeResult(
        episode_num=1,
        title="タイトル",
        content="",
        word_count=0,
        audit_score=0.0,
        audit_passed=False,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
        needs_human_review=False,
    )
    d = episode_summary(ep)
    assert d["content_snippet"] == ""
    assert d["word_count"] == 0
    assert d["audit_passed"] is False


def test_episode_summary_none_content():
    """episode_summary handles None content (converted to empty string)."""
    ep = EpisodeResult(
        episode_num=1,
        title="タイトル",
        content=None,
        word_count=0,
        audit_score=0.0,
        audit_passed=False,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
        needs_human_review=False,
    )
    d = episode_summary(ep)
    assert d["content_snippet"] == ""
    assert d["word_count"] == 0
    assert d["audit_passed"] is False


def test_episode_summary_exact_limit_content():
    """episode_summary handles content exactly at snippet limit."""
    exact_text = "あ" * 200  # EXACTLY at limit
    ep = EpisodeResult(
        episode_num=1,
        title="タイトル",
        content=exact_text,
        word_count=len(exact_text),
        audit_score=80.0,
        audit_passed=True,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
        needs_human_review=False,
    )
    d = episode_summary(ep)
    assert d["content_snippet"] == exact_text
    assert len(d["content_snippet"]) == 200


def test_episode_summary_over_limit_content():
    """episode_summary handles content over snippet limit."""
    over_text = "あ" * 250  # OVER limit
    ep = EpisodeResult(
        episode_num=1,
        title="タイトル",
        content=over_text,
        word_count=len(over_text),
        audit_score=80.0,
        audit_passed=True,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
        needs_human_review=False,
    )
    d = episode_summary(ep)
    assert len(d["content_snippet"]) == 200  # Should be truncated
    assert d["content_snippet"] == "あ" * 200


def test_episode_summary_long_content_snippet():
    """content_snippet is truncated to CONTENT_SNIPPET_CHARS."""
    long_text = "あ" * 300
    ep = EpisodeResult(
        episode_num=1,
        title="タイトル",
        content=long_text,
        word_count=len(long_text),
        audit_score=80.0,
        audit_passed=True,
        rewrite_count=0,
        spice_elements=[SpiceElement(type="unique_metaphor", text="", position=0, priority="low")],
        metadata={},
        needs_human_review=False,
    )
    d = episode_summary(ep)
    assert len(d["content_snippet"]) == 200  # CONTENT_SNIPPET_CHARS
    assert d["content_snippet"] == "あ" * 200


def test_series_to_dict_empty_episodes():
    """series_to_dict works with empty episodes list."""
    s = SeriesResult(
        genre="ジャンル",
        title="タイトル",
        concept="コンセプト",
        total_episodes=0,
        episodes=[],
        bible={},
        plot_outline=[],
        metadata={},
        status="draft",
        created_at=None,
    )
    d = series_to_dict(s)
    assert d["total_episodes"] == 0
    assert d["episodes"] == []
    assert d["status"] == "draft"
    assert d["created_at"] is None


def test_series_to_dict_none_created_at():
    """series_to_dict handles None created_at."""
    s = SeriesResult(
        genre="ジャンル",
        title="タイトル",
        concept="コンセプト",
        total_episodes=5,
        episodes=[],
        bible={},
        plot_outline=[],
        metadata={},
        status="completed",
        created_at=None,
    )
    d = series_to_dict(s)
    assert d["created_at"] is None
    assert d["status"] == "completed"


def test_series_to_dict_empty_bible_metadata_plot():
    """series_to_dict works with empty bible, metadata, and plot_outline."""
    s = SeriesResult(
        genre="",
        title="",
        concept="",
        total_episodes=1,
        episodes=[],
        bible={},
        plot_outline=[],
        metadata={},
        status="draft",
        created_at=None,
    )
    d = series_to_dict(s)
    assert d["bible"] == {}
    assert d["metadata"] == {}
    assert d["plot_outline"] == []


def test_series_to_dict_with_dates():
    """series_to_dict formats created_at as ISO string."""
    import datetime
    dt = datetime.datetime(2023, 1, 1, 12, 0, 0)
    s = SeriesResult(
        genre="ジャンル",
        title="タイトル",
        concept="コンセプト",
        total_episodes=5,
        episodes=[],
        bible={"key": "value"},
        plot_outline=[{"event": "start"}],
        metadata={"meta": 1},
        status="completed",
        created_at=dt,
    )
    d = series_to_dict(s)
    assert d["created_at"] == "2023-01-01T12:00:00"
    assert d["status"] == "completed"


def test_series_to_dict_nested_episode_summary():
    """series_to_dict correctly calls episode_summary for each episode."""
    ep1 = EpisodeResult(
        episode_num=1,
        title="第1話",
        content="内容1",
        word_count=4,
        audit_score=70.0,
        audit_passed=True,
        rewrite_count=1,
        spice_elements=[],
        metadata={"ep1": "meta"},
        needs_human_review=True,
    )
    ep2 = EpisodeResult(
        episode_num=2,
        title="第2話",
        content="内容2",
        word_count=4,
        audit_score=80.0,
        audit_passed=False,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
        needs_human_review=False,
    )
    s = SeriesResult(
        genre="テスト",
        title="シリーズ",
        concept="テスト用",
        total_episodes=2,
        episodes=[ep1, ep2],
        bible={},
        plot_outline=[],
        metadata={},
        status="published",
        created_at=None,
    )
    d = series_to_dict(s)
    assert len(d["episodes"]) == 2
    assert d["episodes"][0]["episode_num"] == 1
    assert d["episodes"][0]["title"] == "第1話"
    assert d["episodes"][0]["word_count"] == 4
    assert d["episodes"][0]["audit_passed"] is True
    assert d["episodes"][0]["rewrite_count"] == 1
    assert d["episodes"][0]["needs_human_review"] is True
    assert d["episodes"][1]["episode_num"] == 2
    assert d["episodes"][1]["title"] == "第2話"
    assert d["episodes"][1]["audit_passed"] is False
    assert d["episodes"][1]["rewrite_count"] == 0
    assert d["episodes"][1]["needs_human_review"] is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
