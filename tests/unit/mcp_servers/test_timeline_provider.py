"""Unit tests for TimelineResourceProvider."""
from __future__ import annotations

from src.mcp_servers.timeline_schemas import TimelineEvent, EpisodeDigest
from src.mcp_servers.providers.timeline_provider import TimelineResourceProvider


def test_timeline_provider_empty():
    provider = TimelineResourceProvider()
    assert provider.read_resource("novel://memory/timeline") == "No timeline events recorded."
    assert "not found" in provider.read_resource("novel://memory/episode/99/digest")
    assert "unsupported" in provider.read_resource("novel://memory/invalid")


def test_timeline_provider_recording_and_reading():
    provider = TimelineResourceProvider()

    # Add events
    provider.add_timeline_event(
        TimelineEvent(timestamp="Day 1", location="Town", description="Met merchant.", characters=["Hero", "Merchant"])
    )
    provider.add_timeline_event(
        TimelineEvent(timestamp="Day 2", location="Forest", description="Fought goblin.", characters=["Hero"])
    )

    timeline_text = provider.read_resource("novel://memory/timeline")
    assert "Day 1" in timeline_text
    assert "Forest" in timeline_text
    assert "Merchant" in timeline_text

    # Record digest
    provider.record_episode_digest(
        EpisodeDigest(episode_num=1, summary="Hero started journey.", footholds_or_foreshadowings=["Mystic Sword"])
    )

    digest_text = provider.read_resource("novel://memory/episode/1/digest")
    assert "Episode 1 Digest" in digest_text
    assert "Hero started journey." in digest_text
    assert "Mystic Sword" in digest_text
