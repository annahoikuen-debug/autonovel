"""Tests for Proposal 1: Dynamic Context Pruning MCP Server (ContextPrunerServer / PruningProvider)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.mcp_servers.providers.pruning_provider import ContextPruningProvider
from src.mcp_servers.pruning_schemas import PruneContextRequest
from src.mcp_servers.pruner_server import PrunerMCPServer
from src.mcp_servers.agent_mcp_bridge import AgentMCPBridge
from src.agents.prompt_composer import PromptComposer


@pytest.fixture
def sample_characters() -> list[dict]:
    return [
        {
            "name": "アルス",
            "aliases": ["勇者アルス", "少年"],
            "role": "主人公・見習い冒険者",
            "personality": "純朴だが内に野心を秘める",
            "speech_pattern": "「〜だ」「やってやる」",
            "secrets_and_flaws": "元奴隷の過去を隠している",
            "importance": "main",
            "relationships": {"エルザ": "頼れる先輩魔法使い", "ギル": "故郷の村長"},
        },
        {
            "name": "エルザ",
            "aliases": ["紅蓮の魔女"],
            "role": "ヒロイン・上級魔術師",
            "personality": "冷静沈着だが情に脆い",
            "speech_pattern": "「〜よ」「甘いわね」",
            "importance": "main",
            "relationships": {"アルス": "後輩"},
        },
        {
            "name": "ギル",
            "aliases": [],
            "role": "始まりの村の村長",
            "personality": "頑固親父",
            "importance": "sub",
            "relationships": {},
        },
        {
            "name": "帝国第十三皇子カイン",
            "aliases": ["カイン殿下"],
            "role": "帝国の冷酷な侵略指導者",
            "personality": "残虐非道",
            "importance": "sub",
            "relationships": {},
        },
        {
            "name": "通りすがりの町人A",
            "aliases": [],
            "role": "モブ市民",
            "personality": "普通",
            "importance": "mob",
            "relationships": {},
        },
    ]


@pytest.fixture
def sample_lore() -> list[dict]:
    return [
        {
            "id": "lore_crimson_cave",
            "title": "紅蓮の洞窟",
            "category": "geography",
            "content": "王都近郊の火山地帯に位置する洞窟。深部には上位炎竜の巣が存在し、高純度の魔光石が採掘される。",
            "keywords": ["紅蓮の洞窟", "火山", "魔光石", "炎竜"],
            "importance": 3,
        },
        {
            "id": "lore_forbidden_magic",
            "title": "古代禁呪・陽炎破",
            "category": "magic",
            "content": "失われた古代文明の超熱波魔法。使用者の命を削るため帝国全土で禁忌とされている。",
            "keywords": ["陽炎破", "古代禁呪", "禁忌魔法"],
            "importance": 4,
        },
        {
            "id": "lore_far_frozen_realm",
            "title": "極北の氷雪帝国",
            "category": "geography",
            "content": "大陸最北端に位置する一年中吹雪の吹き荒れる閉鎖的軍事国家。氷竜の加護を受ける。",
            "keywords": ["極北", "氷雪帝国", "氷竜"],
            "importance": 1,
        },
    ]


@pytest.fixture
def sample_foreshadowings() -> list[dict]:
    return [
        {
            "id": "fore_101",
            "title": "洞窟奥の光る封印石",
            "description": "第3話で設置された封印石。炎竜の目覚めと同期して赤く脈動する。",
            "target_episode": 5,
            "planted_episode": 3,
            "status": "unresolved",
        },
        {
            "id": "fore_102",
            "title": "カインの放った密偵の影",
            "description": "帝国の密偵が王都に潜伏している。",
            "target_episode": 15,
            "planted_episode": 2,
            "status": "unresolved",
        },
        {
            "id": "fore_103",
            "title": "始まりの村の井戸の謎",
            "description": "村の古井戸に隠されていた古文書。第1話で既に回収・読解済み。",
            "target_episode": 2,
            "planted_episode": 1,
            "status": "resolved",
        },
    ]


def test_pruning_provider_characters_classification(sample_characters):
    """プロット出現キャラ・POVキャラ・関係者・除外キャラの仕分け検証"""
    provider = ContextPruningProvider()
    plot = "アルスは紅蓮の洞窟へ足を踏み入れた。背後からはエルザが冷ややかな視線を送っている。"

    req = PruneContextRequest(
        plot_blueprint=plot,
        characters=sample_characters,
        world_lore=[],
        foreshadowings=[],
        pov_character="アルス",
    )
    res = provider.prune_context(req)

    active_names = [c["name"] for c in res.active_characters]
    assert "アルス" in active_names
    assert "エルザ" in active_names

    # ギルはアルス（Active）の relationships に含まれるため peripheral に入る
    peripheral_names = [p["name"] for p in res.peripheral_characters]
    assert "ギル" in peripheral_names

    # カインや通りすがりの町人はプロット言及なし・関係なしなので除外
    assert "通りすがりの町人A" in res.excluded_characters
    assert "帝国第十三皇子カイン" in res.excluded_characters


def test_pruning_provider_lore_filtering(sample_characters, sample_lore):
    """プロット関連世界観のみをスコアリング抽出し、無関係な設定を除外することの検証"""
    provider = ContextPruningProvider()
    plot = "紅蓮の洞窟の奥深く、アルスは禁忌の古代禁呪である陽炎破を解放する決意を固めた。"

    req = PruneContextRequest(
        plot_blueprint=plot,
        characters=sample_characters[:2],
        world_lore=sample_lore,
        foreshadowings=[],
    )
    res = provider.prune_context(req)

    retained_titles = [item["title"] for item in res.relevant_lore]
    assert "紅蓮の洞窟" in retained_titles
    assert "古代禁呪・陽炎破" in retained_titles
    # 極北の氷雪帝国はプロットと無関係なので除外される
    assert "極北の氷雪帝国" not in retained_titles


def test_pruning_provider_foreshadowings_prioritization(sample_foreshadowings):
    """契約伏線（target_episode == current_episode）が最優先抽出されることの検証"""
    provider = ContextPruningProvider()
    plot = "洞窟の最深部、封印石が激しく赤く明滅し始めた。"

    req = PruneContextRequest(
        plot_blueprint=plot,
        characters=[],
        world_lore=[],
        foreshadowings=sample_foreshadowings,
        current_episode=5,
    )
    res = provider.prune_context(req)

    fores = res.prioritized_foreshadowings
    assert len(fores) >= 1
    # 第5話目標の fore_101 が最優先で含まれる
    assert fores[0]["id"] == "fore_101"
    # 解決済みの fore_103 は除外
    fore_ids = [f["id"] for f in fores]
    assert "fore_103" not in fore_ids


def test_pruning_token_reduction_and_budget_packing(sample_characters, sample_lore, sample_foreshadowings):
    """大量のコンテキストがプルーニングにより大幅に削減され、トークン予算内に収まることの検証"""
    provider = ContextPruningProvider()
    plot = "アルスとエルザは紅蓮の洞窟に入り、封印石の前で身構えた。"

    # ダミーで設定を肥大化
    inflated_lore = list(sample_lore) * 5
    inflated_chars = list(sample_characters) * 3

    budget = 400
    req = PruneContextRequest(
        plot_blueprint=plot,
        characters=inflated_chars,
        world_lore=inflated_lore,
        foreshadowings=sample_foreshadowings,
        target_token_budget=budget,
        current_episode=5,
        pov_character="アルス",
    )
    res = provider.prune_context(req)

    assert res.pruned_token_estimate <= budget + 50  # 許容マージン
    assert res.original_token_estimate > res.pruned_token_estimate
    assert res.token_reduction_rate >= 0.40  # 40%以上のトークン削減
    assert res.tokens_saved > 0
    assert "【アルス】" in res.formatted_prompt_context
    assert "紅蓮の洞窟" in res.formatted_prompt_context


def test_pruner_mcp_server_json_rpc(sample_characters, sample_lore):
    """PrunerMCPServer の JSON-RPC 2.0 ハンドラが正常に応答することの検証"""
    server = PrunerMCPServer()

    # 1. prune_context RPC
    req = {
        "jsonrpc": "2.0",
        "method": "prune_context",
        "params": {
            "plot_blueprint": "アルスがエルザと紅蓮の洞窟を探検する。",
            "characters": sample_characters,
            "world_lore": sample_lore,
            "foreshadowings": [],
            "target_token_budget": 1000,
        },
        "id": 100,
    }
    resp = server.handle_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert "result" in resp
    assert "active_characters" in resp["result"]
    assert resp["result"]["token_reduction_rate"] >= 0.0

    # 2. prune_characters RPC
    req_chars = {
        "jsonrpc": "2.0",
        "method": "prune_characters",
        "params": {
            "plot_blueprint": "エルザが歩く。",
            "characters": sample_characters,
        },
        "id": 101,
    }
    resp_chars = server.handle_request(req_chars)
    assert resp_chars["result"]["active_characters"][0]["name"] == "エルザ"

    # 3. 未知のメソッド
    req_unknown = {"jsonrpc": "2.0", "method": "unknown_cmd", "params": {}, "id": 102}
    resp_err = server.handle_request(req_unknown)
    assert resp_err["error"]["code"] == -32601


def test_agent_mcp_bridge_pruning_integration(sample_characters, sample_lore):
    """AgentMCPBridge 経由でのプルーニング呼び出しが正常に動作することの検証"""
    bridge = AgentMCPBridge()
    plot = "アルスは陽炎破の力を使うため、エルザとともに歩き出した。"

    res = bridge.prune_context(
        plot_blueprint=plot,
        characters=sample_characters,
        world_lore=sample_lore,
        pov_character="アルス",
    )

    assert "active_characters" in res
    assert "formatted_prompt_context" in res
    active_names = [c["name"] for c in res["active_characters"]]
    assert "アルス" in active_names
    assert "エルザ" in active_names


@pytest.mark.asyncio
async def test_prompt_composer_with_mcp_pruning(sample_characters, sample_lore, sample_foreshadowings):
    """PromptComposer に enable_mcp_pruning=True を渡した際、動的プルーニングが安全に適用されることの検証"""
    agent_mock = MagicMock()
    pm_mock = MagicMock()
    pm_mock.build_final_writing_prompt = AsyncMock(return_value="GENERATED_PROMPT")
    agent_mock.prompt_manager = pm_mock

    composer = PromptComposer(agent=agent_mock)

    context = {
        "plot": {
            "summary": "アルスとエルザが洞窟で封印石に立ち向かう。",
            "detailed_blueprint": "第5話: アルスとエルザが紅蓮の洞窟深部で光る封印石と対峙する。",
        },
        "target_word_count": 2500,
        "pov_character_name": "アルス",
        "characters_list": sample_characters,
        "world_lore_list": sample_lore,
        "contract_foreshadowings": [sample_foreshadowings[0]],
        "enable_mcp_pruning": True,
        "pruning_token_budget": 1200,
    }

    result = await composer.compose_writing_prompt(
        book_id=1,
        ep_num=5,
        context=context,
    )

    assert "GENERATED_PROMPT" in result
    # プルーニング結果が context に記録されていること
    assert "mcp_pruned_result" in context
    assert "mcp_pruned_stats" in context
    assert context["token_reduction_rate"] >= 0.0

    # PromptManager に渡された char_static_ctx にプルーニング結果が反映されていること
    call_kwargs = pm_mock.build_final_writing_prompt.call_args.kwargs
    assert "【アルス】" in call_kwargs["char_static_ctx"]
