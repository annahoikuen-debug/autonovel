"""Unit tests for TensionAnalyzer."""

from __future__ import annotations

from src.mcp_servers.providers.tension_provider import TensionAnalyzer


def test_tension_analyzer_calm():
    analyzer = TensionAnalyzer()
    score = analyzer.calculate_tension("穏やかな日差しの中で、人々は平和に暮らしていた。")
    assert score.tension_score < 70.0
    assert score.dominant_emotion == "calm"


def test_tension_analyzer_high_tension():
    analyzer = TensionAnalyzer()
    text = "敵が迫る！ 剣を抜け、走れ！ 血が流れる絶望の瞬間だ！"
    score = analyzer.calculate_tension(text, target_tension=105.0)
    assert score.tension_score >= 70.0
    assert score.dominant_emotion == "tension"
    assert "Warning" in score.feedback


def test_tension_analyzer_polarity():
    analyzer = TensionAnalyzer()
    pos_score = analyzer.calculate_polarity("希望と勝利の光に満ちた笑み。")
    assert pos_score > 0.0

    neg_score = analyzer.calculate_polarity("冷たい闇の中での敗北と涙。")
    assert neg_score < 0.0
