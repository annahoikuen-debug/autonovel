"""Tests for Proposal 7: Tension Curve & Emotional Arc MCP Server (TensionMCPServer / TensionAnalyzer)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.mcp_servers.providers.tension_provider import TensionAnalyzer
from src.mcp_servers.tension_server import TensionMCPServer
from src.mcp_servers.agent_mcp_bridge import AgentMCPBridge
from src.agents.prompt_composer import PromptComposer


@pytest.fixture
def sample_dramatic_story() -> str:
    """起承転結・カタルシスが明瞭なサンプルテキスト"""
    part1 = "王都の朝は静かに明けた。アルスは路地裏のパン屋から漂う香ばしい匂いに目を細め、穏やかな風を感じていた。" * 5
    part2 = "だが突如、地面が不気味に鳴動した。逃げる群衆の悲鳴。遠くから迫る影。事態は急速に悪化していた。" * 5
    part3 = "「死ねぇ！」刃が閃光を放ち、血煙が舞う。激痛が走る中、アルスは咆哮とともに全力で剣を振り下ろした。死闘が交錯する。" * 5
    part4 = "激闘が終わり、静寂が戻った。敵は地に伏し、温かい朝日が差し込む。アルスは深く息を吐き、安堵の微笑みを浮かべた。" * 5
    return f"{part1}\n{part2}\n{part3}\n{part4}"


@pytest.fixture
def sample_flat_story() -> str:
    """起伏がなく平坦なサンプルテキスト（中だるみ検知テスト用）"""
    return "彼は本を読んだ。静かな部屋だった。時計の針が進む。ただそれだけだった。特に何も起こらなかった。" * 20


def test_tension_analyzer_single_text_measurement():
    """単一テキストの緊迫度・感情極性・主要感情測定の検証"""
    analyzer = TensionAnalyzer()

    high_text = "逃げるんだ！早く走れ！血が流れている！絶望的な戦いだ！"
    high_res = analyzer.calculate_tension(high_text)
    assert high_res.tension_score >= 65.0
    assert high_res.dominant_emotion == "tension"

    peaceful_text = "温かいスープを飲んで、二人は顔を見合わせて微笑んだ。勝利の喜びと希望に満ちていた。"
    peace_res = analyzer.calculate_tension(peaceful_text)
    assert peace_res.tension_score <= 45.0
    assert peace_res.polarity > 0.0
    assert peace_res.dominant_emotion in ["joy", "calm"]


def test_generate_target_curve_presets():
    """目標感情曲線プリセットの生成とプロンプト指示テキストの検証"""
    analyzer = TensionAnalyzer()

    curve = analyzer.generate_target_curve(curve_type="climax_catharsis")
    assert curve.curve_type == "climax_catharsis"
    assert len(curve.target_points) == 4
    # クライマックス（第3幕）が最高値
    assert curve.target_points[2] > curve.target_points[0]
    assert curve.target_points[2] > curve.target_points[3]
    assert "### 【本話の感情曲線・テンション設計" in curve.prompt_directive

    cliff_curve = analyzer.generate_target_curve(curve_type="cliffhanger")
    # クリフハンガーは最終幕が最高値
    assert cliff_curve.target_points[3] > cliff_curve.target_points[0]


def test_analyze_novel_arc_climax_fit(sample_dramatic_story):
    """起承転結の文章に対して感情曲線分析が正しく動作し、高適合度とピーク検出を行うことの検証"""
    analyzer = TensionAnalyzer()
    result = analyzer.analyze_novel_arc(sample_dramatic_story, curve_type="climax_catharsis")

    assert len(result.segments) == 4
    # 第3幕（クライマックス）のテンションが序盤より明らかに高いこと
    assert result.segments[2].tension_score > result.segments[0].tension_score
    # 中だるみ判定が False であること
    assert result.flatness_detected is False
    assert result.curve_fit_score >= 0.55
    assert result.peak_segment_index in [1, 2]  # ピークが展開またはクライマックス


def test_analyze_novel_arc_flatness_detection(sample_flat_story):
    """起伏のない平坦な文章に対して flatness_detected=True と改善ガイダンスが出力されることの検証"""
    analyzer = TensionAnalyzer()
    result = analyzer.analyze_novel_arc(sample_flat_story, curve_type="climax_catharsis")

    assert result.flatness_detected is True
    assert any("起伏不足" in g or "中だるみ" in g for g in result.actionable_guidance)


def test_tension_mcp_server_json_rpc(sample_dramatic_story):
    """TensionMCPServer の JSON-RPC 2.0 ハンドラが正常に応答することの検証"""
    server = TensionMCPServer()

    # 1. generate_target_curve RPC
    req1 = {
        "jsonrpc": "2.0",
        "method": "generate_target_curve",
        "params": {"curve_type": "rollercoaster"},
        "id": 1,
    }
    resp1 = server.handle_request(req1)
    assert resp1["jsonrpc"] == "2.0"
    assert resp1["result"]["curve_type"] == "rollercoaster"
    assert len(resp1["result"]["target_points"]) == 4

    # 2. analyze_novel_arc RPC
    req2 = {
        "jsonrpc": "2.0",
        "method": "analyze_novel_arc",
        "params": {"text": sample_dramatic_story, "curve_type": "climax_catharsis"},
        "id": 2,
    }
    resp2 = server.handle_request(req2)
    assert resp2["result"]["curve_fit_score"] >= 0.5
    assert len(resp2["result"]["segments"]) == 4

    # 3. check_emotional_tension RPC (既存互換)
    req3 = {
        "jsonrpc": "2.0",
        "method": "check_emotional_tension",
        "params": {"text": "走れ！逃げるんだ！"},
        "id": 3,
    }
    resp3 = server.handle_request(req3)
    assert resp3["result"]["tension_score"] > 0.0


def test_agent_mcp_bridge_tension_integration(sample_dramatic_story):
    """AgentMCPBridge 経由での感情曲線ツール呼び出し検証"""
    bridge = AgentMCPBridge()

    curve_res = bridge.generate_target_curve("climax_catharsis")
    assert "target_points" in curve_res
    assert "prompt_directive" in curve_res

    arc_res = bridge.analyze_novel_arc(sample_dramatic_story, "climax_catharsis")
    assert "curve_fit_score" in arc_res
    assert "segments" in arc_res


@pytest.mark.asyncio
async def test_prompt_composer_with_emotional_curve_directive():
    """PromptComposer に emotional_curve_type を渡した際、プロンプトに目標曲線指示が注入されることの検証"""
    agent_mock = MagicMock()
    pm_mock = MagicMock()
    pm_mock.build_final_writing_prompt = AsyncMock(return_value="BASE_PROMPT")
    agent_mock.prompt_manager = pm_mock

    composer = PromptComposer(agent=agent_mock)
    context = {
        "plot": {"summary": "決戦の時が来た。"},
        "target_word_count": 2000,
        "emotional_curve_type": "climax_catharsis",
    }

    result = await composer.compose_writing_prompt(
        book_id=1,
        ep_num=10,
        context=context,
    )

    assert "BASE_PROMPT" in result
    # プロンプト内に感情曲線の指示が注入されていること
    assert "【本話の感情曲線・テンション設計" in result
    assert "mcp_target_curve" in context
    assert context["mcp_target_curve"]["curve_type"] == "climax_catharsis"
