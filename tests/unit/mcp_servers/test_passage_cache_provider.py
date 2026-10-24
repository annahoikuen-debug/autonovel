"""Unit tests for PassageCacheProvider."""

from __future__ import annotations

from src.mcp_servers.passage_cache_schemas import CachedPassage, PassageSearchRequest
from src.mcp_servers.providers.passage_cache_provider import PassageCacheProvider


def test_passage_cache_provider_empty():
    provider = PassageCacheProvider()
    req = PassageSearchRequest(query="tavern", top_k=2)
    res = provider.search_similar_passages(req)
    assert len(res.passages) == 0
    assert "Found 0" in res.search_summary


def test_passage_cache_provider_search_and_stats():
    provider = PassageCacheProvider()
    p1 = CachedPassage(
        passage_id="p1",
        intent="Tavern entrance",
        body="The wooden door creaked open, smelling of warm ale and roasted meat.",
        tags=["tavern"],
    )
    p2 = CachedPassage(
        passage_id="p2",
        intent="Forest battle",
        body="Shadows flickered among ancient trees as blades clashed.",
        tags=["battle"],
    )
    provider.register_passage(p1)
    provider.register_passage(p2)

    # Search with tag filter
    req = PassageSearchRequest(query="ale", top_k=5, tags=["tavern"])
    res = provider.search_similar_passages(req)
    assert len(res.passages) == 1
    assert res.passages[0].passage_id == "p1"
    assert res.passages[0].hit_count == 1
