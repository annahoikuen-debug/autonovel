"""Unit tests for Timeline URI parser and schemas."""
from __future__ import annotations

from src.mcp_servers.timeline_schemas import (
    TimelineEvent,
    EpisodeDigest,
    parse_memory_uri,
)


def test_parse_memory_uri_timeline():
    res = parse_memory_uri("novel://memory/timeline")
    assert res["type"] == "timeline"


def test_parse_memory_uri_episode_digest():
    res = parse_memory_uri("novel://memory/episode/5/digest")
    assert res["type"] == "episode_digest"
    assert res["episode_num"] == 5


def test_parse_memory_uri_unknown():
    res = parse_memory_uri("novel://memory/invalid/uri")
    assert res["type"] == "unknown"


def test_schemas_instantiation():
    event = TimelineEvent(timestamp="Day 1", location="Castle", description="Hero arrived.")
    assert event.location == "Castle"

    digest = EpisodeDigest(episode_num=1, summary="Beginning of adventure.")
    assert digest.episode_num == 1
    assert digest.summary == "Beginning of adventure."
