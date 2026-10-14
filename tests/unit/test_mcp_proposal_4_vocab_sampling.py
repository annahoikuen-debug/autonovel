"""Tests for MCP Proposal 4: Sensory & Erotic Vocabulary Sampling Server."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.mcp_servers.agent_mcp_bridge import AgentMCPBridge
from src.mcp_servers.vocab_server import VocabMCPServer
from src.mcp_servers.providers.vocab_provider import SensoryVocabProvider
from src.mcp_servers.vocab_schemas import SensoryWord
from src.engine.prompts.erotic_specialist import EroticSpecialist


def test_vocab_provider_intensity_sampling_mild_vs_intense():
    """低強度(0.2)と高強度(0.9)で、サンプリングされる語彙の強度が適切に切り替わること。"""
    provider = SensoryVocabProvider()

    # 低強度（穏やか・日常・初恋）
    res_mild = provider.sample_by_intensity(category="metaphor", intensity=0.2, count=5, seed=42)
    assert res_mild.count > 0
    avg_mild = sum(item["intensity"] for item in res_mild.items) / res_mild.count
    assert avg_mild <= 0.70

    # 高強度（極限・境界崩壊・重力消失）
    res_intense = provider.sample_by_intensity(category="metaphor", intensity=0.95, count=5, seed=42)
    assert res_intense.count > 0
    avg_intense = sum(item["intensity"] for item in res_intense.items) / res_intense.count
    assert avg_intense >= 0.75
    assert avg_intense > avg_mild


def test_vocab_provider_category_filtering():
    """指定カテゴリ（psychological, onomatopoeia 等）のみがサンプリングされること。"""
    provider = SensoryVocabProvider()

    res_psy = provider.sample_by_intensity(category="psychological", intensity=0.5, count=4)
    assert all(item["category"] == "psychological" for item in res_psy.items)

    res_ono = provider.sample_by_intensity(category="onomatopoeia", intensity=0.8, count=4)
    assert all(item["category"] == "onomatopoeia" for item in res_ono.items)


def test_vocab_provider_seed_reproducibility():
    """同一 seed を指定した場合、サンプリング結果が完全に再現されること。"""
    provider = SensoryVocabProvider()

    res1 = provider.sample_by_intensity(intensity=0.7, count=5, seed=12345)
    res2 = provider.sample_by_intensity(intensity=0.7, count=5, seed=12345)

    words1 = [item["word"] for item in res1.items]
    words2 = [item["word"] for item in res2.items]
    assert words1 == words2


def test_vocab_mcp_server_sample_rpc():
    """VocabMCPServer の JSON-RPC ハンドラーで sample_by_intensity が正しく動作すること。"""
    provider = SensoryVocabProvider()
    server = VocabMCPServer(provider)

    req = {
        "jsonrpc": "2.0",
        "method": "sample_by_intensity",
        "params": {
            "category": "metaphor",
            "intensity": 0.85,
            "genre": "erotic",
            "count": 3,
        },
        "id": 201,
    }
    resp = server.handle_request(req)
    assert resp["id"] == 201
    assert "result" in resp
    assert resp["result"]["count"] == 3
    assert len(resp["result"]["items"]) == 3


def test_agent_mcp_bridge_sample_vocab_integration():
    """AgentMCPBridge を通じて動的サンプリングが取得できること。"""
    bridge = AgentMCPBridge()
    res = bridge.sample_vocab_by_intensity(category="metaphor", intensity=0.6, count=4)

    assert "items" in res
    assert len(res["items"]) > 0


def test_erotic_specialist_prompt_builder_with_mcp_vocab():
    """EroticSpecialist に use_mcp_vocab_sampling=True を渡した際、動的推奨ブロックが生成されること。"""
    specialist = EroticSpecialist()

    # ダミーカーブとビート
    mock_beat = MagicMock()
    mock_beat.phase = "buildup"
    mock_beat.desire_level = 3
    mock_beat.sensory_focus = ["touch", "temperature"]
    mock_beat.consent_state = "consensual"
    mock_beat.sub_beats = []

    mock_curve = MagicMock()
    mock_curve.target_intensity = 3
    mock_curve.beats = [mock_beat]

    context = {
        "platform_preset": "kakuyomu_romance",
        "use_mcp_vocab_sampling": True,
    }

    prompt = specialist.build_scene_prompt(mock_curve, context=context)

    # 動的推奨の案内が含まれていること
    assert "動的推奨の官能比喩表現" in prompt
    assert "動的推奨の心理描写表現" in prompt
    assert "動的推奨の擬音・擬態表現" in prompt
