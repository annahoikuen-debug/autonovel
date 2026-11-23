"""
改善案1: 序盤フックエンジン配線のユニットテスト。

フラグ ENABLE_SEQ_HOOK_WIRING の ON/OFF による挙動を検証する。
"""

from __future__ import annotations

from unittest.mock import patch


from src.easy_mode.hooks import build_hook_directive, evaluate_and_maybe_rewrite, should_apply_hook


class TestShouldApplyHook:
    """should_apply_hook の判定テスト。"""

    @patch("src.easy_mode.hooks.settings")
    def test_ep1_flag_on(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        assert should_apply_hook(1) is True

    @patch("src.easy_mode.hooks.settings")
    def test_ep2_flag_on(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        assert should_apply_hook(2) is True

    @patch("src.easy_mode.hooks.settings")
    def test_ep3_flag_on(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        assert should_apply_hook(3) is True

    @patch("src.easy_mode.hooks.settings")
    def test_ep4_flag_on_is_false(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        assert should_apply_hook(4) is False

    @patch("src.easy_mode.hooks.settings")
    def test_ep1_flag_off_is_false(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = False
        assert should_apply_hook(1) is False


class TestEvaluateAndMaybeRewrite:
    """evaluate_and_maybe_rewrite の挙動テスト。"""

    @patch("src.easy_mode.hooks.settings")
    def test_flag_off_returns_none_metrics(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = False
        text, metrics = evaluate_and_maybe_rewrite("平穏な一日でした。", 1)
        assert text == "平穏な一日でした。"
        assert metrics is None

    @patch("src.easy_mode.hooks.settings")
    def test_ep4_flag_on_returns_none_metrics(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        text, metrics = evaluate_and_maybe_rewrite("平穏な一日でした。", 4)
        assert text == "平穏な一日でした。"
        assert metrics is None

    @patch("src.easy_mode.hooks.settings")
    def test_peaceful_text_requires_rewrite(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        text, metrics = evaluate_and_maybe_rewrite("そして彼は穏やかに眠りについた。", 1)
        assert metrics is not None
        assert metrics.requires_rewrite is True
        assert metrics.score < 100.0
        assert "リライト" in metrics.reason or "クリフハンガー" in metrics.reason

    @patch("src.easy_mode.hooks.settings")
    def test_crisis_text_no_rewrite(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        text, metrics = evaluate_and_maybe_rewrite("背後から刃が振り下ろされた！", 1)
        assert metrics is not None
        assert metrics.requires_rewrite is False

    @patch("src.easy_mode.hooks.settings")
    def test_hook_metrics_fields(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        _, metrics = evaluate_and_maybe_rewrite("おやすみ、明日も頑張ろう。", 2)
        assert metrics is not None
        assert metrics.ep_num == 2
        assert metrics.hook_type in ("crisis", "shocking_truth", "triumph_trigger", "peaceful")
        assert 0.0 <= metrics.score <= 100.0
        assert isinstance(metrics.reason, str)
        assert isinstance(metrics.tail_sentence, str)


class TestBuildHookDirective:
    """build_hook_directive のテスト。"""

    def test_no_rewrite_returns_empty(self):
        from src.models.seq_hook import HookMetrics

        metrics = HookMetrics(
            ep_num=1,
            hook_type="crisis",
            score=90.0,
            requires_rewrite=False,
            reason="引きOK",
            tail_sentence="背後から刃が振り下ろされた！",
        )
        assert build_hook_directive(metrics) == ""

    def test_rewrite_returns_directive(self):
        from src.models.seq_hook import HookMetrics

        metrics = HookMetrics(
            ep_num=1,
            hook_type="peaceful",
            score=35.0,
            requires_rewrite=True,
            reason="平穏な結末です",
            tail_sentence="おやすみ。",
        )
        directive = build_hook_directive(metrics)
        assert "リライト指令" in directive
        assert "peaceful" in directive
