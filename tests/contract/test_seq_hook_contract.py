"""
改善案1: 序盤フック配線の契約テスト。

フラグ ENABLE_SEQ_HOOK_WIRING が OFF の間は、現行挙動とバイト同一を維持する。
"""

from __future__ import annotations

from unittest.mock import patch

from src.domain.entities.easy_mode import GenerationResponse
from src.easy_mode.hooks import evaluate_and_maybe_rewrite, should_apply_hook


class TestSeqHookContractFlagOff:
    """フラグOFF時の契約テスト。"""

    @patch("src.easy_mode.hooks.settings")
    def test_should_apply_hook_false_when_flag_off(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = False
        assert should_apply_hook(1) is False
        assert should_apply_hook(2) is False
        assert should_apply_hook(3) is False

    @patch("src.easy_mode.hooks.settings")
    def test_evaluate_and_maybe_rewrite_byte_identical_when_flag_off(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = False
        original = "平穏な一日でした。おやすみ。"
        text, metrics = evaluate_and_maybe_rewrite(original, 1)
        assert text == original  # バイト同一（変更なし）
        assert metrics is None

    def test_generation_response_has_optional_hook_fields(self):
        # GenerationResponse に hook_metrics / ctr_metrics / ctr_suggestions が
        # Optional / default_factory であり、未指定でもインスタンス化できること
        resp = GenerationResponse(task_id="task-123", output="本文")
        assert resp.hook_metrics is None
        assert resp.ctr_metrics is None
        assert resp.ctr_suggestions == []

    @patch("src.easy_mode.hooks.settings")
    def test_hook_metrics_can_be_set(self, mock_settings):
        mock_settings.ENABLE_SEQ_HOOK_WIRING = True
        resp = GenerationResponse(
            task_id="task-123",
            output="本文",
            hook_metrics={
                "ep_num": 1,
                "hook_type": "crisis",
                "score": 85.0,
                "requires_rewrite": False,
                "reason": "引きOK",
                "tail_sentence": "背後から刃が振り下ろされた！",
            },
        )
        assert resp.hook_metrics is not None
        assert resp.hook_metrics["ep_num"] == 1
