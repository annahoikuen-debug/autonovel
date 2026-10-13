"""Unit tests for Lore/Bible MCP Server."""
from __future__ import annotations

from src.mcp_servers.schemas import CharacterProfile, WorldBibleSection, LoreQueryRequest
from src.mcp_servers.providers.lore_provider import LoreProvider
from src.mcp_servers.lore_server import LoreMCPServer


def test_lore_provider_registration_and_query():
    provider = LoreProvider()

    char = CharacterProfile(
        name="Alice",
        aliases=["アリス"],
        role="Protagonist",
        appearance="Silver hair",
        personality="Brave and kind",
        speech_pattern="Desu wa",
        secrets_and_flaws="Has a dark past",
    )
    provider.register_character(char)

    section = WorldBibleSection(
        section_id="world_rule_1",
        title="Magic System",
        content="Mana flows through all living things.",
        tags=["magic", "world"],
    )
    provider.register_bible_section(section)

    # Query matching character
    req = LoreQueryRequest(query="Alice is amazing", character_names=["Alice"])
    res = provider.query(req)
    assert len(res.characters) == 1
    assert res.characters[0].name == "Alice"
    assert "Alice" in res.compressed_summary

    # Query matching section
    req2 = LoreQueryRequest(query="Tell me about magic system", tags=["magic"])
    res2 = provider.query(req2)
    assert len(res2.bible_sections) == 1
    assert res2.bible_sections[0].section_id == "world_rule_1"


def test_mcp_server_json_rpc():
    provider = LoreProvider()
    server = LoreMCPServer(provider)

    # Register character via JSON-RPC
    reg_req = {
        "jsonrpc": "2.0",
        "method": "register_character",
        "params": {
            "name": "Bob",
            "aliases": ["ボブ"],
            "role": "Antagonist",
            "personality": "Cunning",
        },
        "id": 1,
    }
    resp = server.handle_request(reg_req)
    assert resp["result"]["status"] == "success"

    # Query via JSON-RPC
    query_req = {
        "jsonrpc": "2.0",
        "method": "query_lore",
        "params": {
            "query": "Bob appears",
            "character_names": ["Bob"],
        },
        "id": 2,
    }
    resp2 = server.handle_request(query_req)
    assert len(resp2["result"]["characters"]) == 1
    assert resp2["result"]["characters"][0]["name"] == "Bob"

    # Unknown method
    unknown_req = {
        "jsonrpc": "2.0",
        "method": "unknown_method",
        "params": {},
        "id": 3,
    }
    resp3 = server.handle_request(unknown_req)
    assert "error" in resp3
    assert resp3["error"]["code"] == -32601

    # Exception handling (malformed params or unexpected error)
    err_req = {
        "jsonrpc": "2.0",
        "method": "register_character",
        "params": None,  # Will cause type error
        "id": 4,
    }
    resp4 = server.handle_request(err_req)
    assert "error" in resp4
    assert resp4["error"]["code"] == -32603

    # Register bible section via JSON-RPC
    bible_req = {
        "jsonrpc": "2.0",
        "method": "register_bible_section",
        "params": {
            "section_id": "rule_2",
            "title": "History",
            "content": "Long ago...",
            "tags": ["history"],
        },
        "id": 5,
    }
    resp5 = server.handle_request(bible_req)
    assert resp5["result"]["status"] == "success"

