"""Unit tests for AgentMCPBridge."""

from __future__ import annotations


from src.mcp_servers.agent_mcp_bridge import AgentMCPBridge
from src.mcp_servers.schemas import CharacterProfile, WorldBibleSection
from src.mcp_servers.vocab_schemas import SensoryWord


def test_agent_mcp_bridge_workflow():
    bridge = AgentMCPBridge()

    # Register lore
    bridge.lore_server.provider.register_character(CharacterProfile(name="ルナ", role="騎士"))
    bridge.lore_server.provider.register_bible_section(
        WorldBibleSection(section_id="sec1", title="王国史", content="王国は三つの剣に守られている。", tags=["history"])
    )

    # Test lore query
    lore_res = bridge.get_lore_context("王国史", character_names=["ルナ"], tags=["history"])
    assert len(lore_res.get("characters", [])) == 1
    assert len(lore_res.get("bible_sections", [])) == 1

    # Register vocab
    bridge.vocab_server.provider.register_words(
        "fantasy", [SensoryWord(word="鋼鉄の冷たさ", category="tactile", example_sentence="剣の冷たさが掌に伝わる。")]
    )

    # Test vocab suggestion
    sugs = bridge.suggest_metaphors("冷たさ", "fantasy")
    assert len(sugs) == 1

    # Test tension measurement
    tension_res = bridge.measure_tension("緊迫した空気が漂う中、敵が刃を抜いた！")
    assert "tension_score" in tension_res

    # Test static audit
    audit_res = bridge.audit_static_rules("これはテスト文章です。")
    assert "is_compliant" in audit_res
