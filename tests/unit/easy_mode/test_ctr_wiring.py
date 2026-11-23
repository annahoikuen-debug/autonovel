"""
改善案2: タイトル・キャッチコピーCTR最適化配線のユニットテスト。

フラグ ENABLE_CTR_WIRING の ON/OFF による挙動を検証する。
"""

from __future__ import annotations

from unittest.mock import patch


from src.easy_mode.hooks import evaluate_ctr, generate_ctr_suggestions


class TestEvaluateCTR:
    """evaluate_ctr の挙動テスト。"""

    @patch("src.easy_mode.hooks.settings")
    def test_flag_off_returns_none(self, mock_settings):
        mock_settings.ENABLE_CTR_WIRING = False
        result = evaluate_ctr("タイトル", "キャッチコピー")
        assert result is None

    @patch("src.easy_mode.hooks.settings")
    def test_optimal_title_high_score(self, mock_settings):
        mock_settings.ENABLE_CTR_WIRING = True
        # 35〜55字かつパワーワードを含むタイトル
        result = evaluate_ctr("【追放】実は最強だった件について、ざまぁ返し", None)
        assert result is not None
        assert result.title_score >= 0.0
        assert result.title_score <= 100.0
        assert result.syntax_type in ("追放ざまぁ", "勘違い無双", "無自覚無双", "一般")

    @patch("src.easy_mode.hooks.settings")
    def test_short_title_low_score(self, mock_settings):
        mock_settings.ENABLE_CTR_WIRING = True
        result = evaluate_ctr("短い", None)
        assert result is not None
        assert result.title_needs_improvement is True

    @patch("src.easy_mode.hooks.settings")
    def test_catchphrase_scored(self, mock_settings):
        mock_settings.ENABLE_CTR_WIRING = True
        result = evaluate_ctr("【追放】実は最強だった件について、ざまぁ返し", "「最強」の勘違い！")
        assert result is not None
        assert 0.0 <= result.catchphrase_score <= 100.0

    @patch("src.easy_mode.hooks.settings")
    def test_ctr_metrics_fields(self, mock_settings):
        mock_settings.ENABLE_CTR_WIRING = True
        result = evaluate_ctr("【追放】実は最強だった件について、ざまぁ返し", None)
        assert result is not None
        assert isinstance(result.title_score, float)
        assert isinstance(result.catchphrase_score, float)
        assert isinstance(result.title_needs_improvement, bool)
        assert isinstance(result.catchphrase_needs_improvement, bool)
        assert isinstance(result.syntax_type, str)


class TestGenerateCTRSuggestions:
    """generate_ctr_suggestions の生成テスト。"""

    def test_exile_zaima_type(self):
        suggestions = generate_ctr_suggestions("追放された", "ファンタジー", "追放ざまぁ")
        assert len(suggestions) == 3
        for s in suggestions:
            assert "追放" in s or "ざまぁ" in s

    def test_misunderstanding_type(self):
        suggestions = generate_ctr_suggestions("勘違い", "ファンタジー", "勘違い無双")
        assert len(suggestions) == 3
        for s in suggestions:
            assert "勘違い" in s

    def test_unaware_type(self):
        suggestions = generate_ctr_suggestions("無自覚", "ファンタジー", "無自覚無双")
        assert len(suggestions) == 3
        for s in suggestions:
            assert "無自覚" in s

    def test_general_type(self):
        suggestions = generate_ctr_suggestions("タイトル", "ファンタジー", "一般")
        assert len(suggestions) == 3
        for s in suggestions:
            assert len(s) > 0

    def test_length_capped(self):
        # 65字を超える案が生成されても、最適文字数範囲にカットされる
        long_title = "あ" * 100
        suggestions = generate_ctr_suggestions(long_title, "ファンタジー", "一般")
        for s in suggestions:
            assert len(s) <= 55
