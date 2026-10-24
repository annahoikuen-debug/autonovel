"""Integration test demonstrating the combined workflow of MCP servers (Lore, Vocab, Tension, Timeline, Audit)."""

from __future__ import annotations

import pytest

from src.mcp_servers.lore_server import LoreMCPServer
from src.mcp_servers.providers.lore_provider import LoreProvider
from src.mcp_servers.vocab_server import VocabMCPServer
from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider
from src.mcp_servers.tension_server import TensionMCPServer
from src.mcp_servers.providers.tension_provider import TensionAnalyzer
from src.mcp_servers.timeline_server import TimelineMCPServer
from src.mcp_servers.providers.timeline_provider import TimelineResourceProvider
from src.mcp_servers.audit_mcp_server import AuditMCPServer
from src.mcp_servers.providers.audit_provider import AuditProvider


@pytest.mark.asyncio
async def test_mcp_servers_collaborative_workflow():
    """Demonstrates how an LLM or writing pipeline interacts with multiple MCP servers

    in a cohesive sequence:
    1. Lore: Lookup world rules and character profiles.
    2. Vocab: Fetch sensory metaphors for the scene genre.
    3. Tension: Measure emotional tension and friction of drafted text.
    4. Timeline: Record episode digest and query the timeline URI.
    5. Audit: Perform local static metrics/rule checks before calling expensive LLMs.
    """
    # Initialize providers and servers
    lore_provider = LoreProvider()
    lore_server = LoreMCPServer(lore_provider)

    vocab_provider = SensoryVocabProvider()
    vocab_server = VocabMCPServer(vocab_provider)

    tension_analyzer = TensionAnalyzer()
    tension_server = TensionMCPServer(tension_analyzer)

    timeline_provider = TimelineResourceProvider()
    timeline_server = TimelineMCPServer(timeline_provider)

    audit_provider = AuditProvider()
    audit_server = AuditMCPServer(audit_provider)

    # --- Step 1: Lore Lookup ---
    from src.mcp_servers.schemas import CharacterProfile, WorldBibleSection

    lore_provider.register_bible_section(
        WorldBibleSection(
            section_id="magic_system",
            title="魔法体系",
            content="詠唱なしの即時発動型元素魔法。ただし魔力枯渇の危険あり。",
            tags=["magic"],
        )
    )
    lore_provider.register_character(CharacterProfile(name="アリス", role="魔導士", personality="クールで仲間思い"))

    query_req = {
        "jsonrpc": "2.0",
        "method": "query_lore",
        "params": {"query": "magic system", "character_names": ["アリス"], "tags": ["magic"]},
        "id": 1,
    }
    query_resp = lore_server.handle_request(query_req)
    assert len(query_resp["result"]["characters"]) == 1
    assert len(query_resp["result"]["bible_sections"]) == 1
    assert "詠唱なし" in query_resp["result"]["bible_sections"][0]["content"]

    # --- Step 2: Vocabulary / Sensory Metaphor Suggestion ---
    from src.mcp_servers.vocab_schemas import SensoryWord

    vocab_provider.register_words(
        genre="fantasy",
        words=[
            SensoryWord(
                word="冷たい石壁の感触",
                category="tactile",
                example_sentence="背中に当たる冷たい石壁が意識を覚醒させる。",
                nuance="tension",
            )
        ],
    )
    vocab_req = {
        "jsonrpc": "2.0",
        "method": "suggest_metaphors",
        "params": {"keyword": "石壁", "genre": "fantasy"},
        "id": 2,
    }
    vocab_resp = vocab_server.handle_request(vocab_req)
    assert len(vocab_resp["result"]["suggestions"]) == 1

    # --- Step 3: Draft Scene Text ---
    draft_text = "冷たい石壁の感触が背中を走る。アリスは無言で手を伸ばし、詠唱なしで炎の球体を創り出した。"

    # --- Step 4: Tension & Emotion Measurement ---
    tension_req = {
        "jsonrpc": "2.0",
        "method": "check_emotional_tension",
        "params": {"text": draft_text, "target_tension": 60.0},
        "id": 3,
    }
    tension_resp = tension_server.handle_request(tension_req)
    assert "tension_score" in tension_resp["result"]

    # --- Step 5: Timeline & Episode Digest Logging ---
    from src.mcp_servers.timeline_schemas import EpisodeDigest

    timeline_provider.record_episode_digest(
        EpisodeDigest(
            episode_num=5, summary="アリスがダンジョン内で魔法を発動した。", footholds_or_foreshadowings=["魔法発動"]
        )
    )

    # Read timeline URI resource
    uri_req = {
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "novel://memory/episode/5/digest"},
        "id": 5,
    }
    uri_resp = timeline_server.handle_request(uri_req)
    assert "アリスがダンジョン内" in uri_resp["result"]["contents"][0]["text"]

    # --- Step 6: Local Static Audit / Compliance Check ---
    audit_req = {
        "jsonrpc": "2.0",
        "method": "audit_text",
        "params": {"text": draft_text, "active_rules": []},
        "id": 6,
    }
    audit_resp = audit_server.handle_request(audit_req)
    assert audit_resp["result"]["is_compliant"] is True
    assert "score" in audit_resp["result"]

    print("All MCP servers collaborated successfully in workflow simulation!")
