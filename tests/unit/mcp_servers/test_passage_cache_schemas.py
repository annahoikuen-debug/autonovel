"""Unit tests for passage cache schemas."""
from __future__ import annotations

from src.mcp_servers.passage_cache_schemas import (
    CachedPassage,
    PassageSearchRequest,
    PassageSearchResponse,
)


def test_passage_cache_schemas_instantiation():
    passage = CachedPassage(
        passage_id="p1",
        intent="Hero enters tavern",
        body="The wooden door creaked open, smelling of ale.",
        tags=["tavern", "opening"]
    )
    assert passage.passage_id == "p1"
    assert passage.hit_count == 0

    req = PassageSearchRequest(query="tavern opening", top_k=2, tags=["tavern"])
    assert req.top_k == 2

    res = PassageSearchResponse(passages=[passage], search_summary="Found 1 passage.")
    assert len(res.passages) == 1
