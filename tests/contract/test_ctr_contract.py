"""
改善案2: タイトル・キャッチコピーCTR配線の契約テスト。

フラグ ENABLE_CTR_WIRING が OFF の間は、現行挙動とバイト同一を維持する。
"""

from __future__ import annotations

from unittest.mock import patch

from src.domain.entities.easy_mode import GenerationResponse
from src.easy_mode.hooks import evaluate_ctr


class TestCTRContractFlagOff:
    """フラグOFF時の契約テスト。"""

    @patch("src.easy_mode.hooks.settings")
    def test_evaluate_ctr_none_when_flag_off(self, mock_settings):
        mock_settings.ENABLE_CTR_WIRING = False
        assert evaluate_ctr("タイトル", "キャッチコピー") is None

    def test_generation_response_has_optional_ctr_fields(self):
        # GenerationResponse に ctr_metrics / ctr_suggestions が
        # Optional / default_factory であり、未指定でもインスタンス化できること
        resp = GenerationResponse(task_id="task-123", output="本文")
        assert resp.ctr_metrics is None
        assert resp.ctr_suggestions == []

    def test_generation_response_can_set_ctr_fields(self):
        resp = GenerationResponse(
            task_id="task-123",
            output="本文",
            ctr_metrics={
                "title_score": 75.0,
                "catchphrase_score": 60.0,
                "title_needs_improvement": False,
                "catchphrase_needs_improvement": False,
                "syntax_type": "追放ざまぁ",
            },
            ctr_suggestions=["案1", "案2", "案3"],
        )
        assert resp.ctr_metrics is not None
        assert resp.ctr_metrics["title_score"] == 75.0
        assert resp.ctr_suggestions == ["案1", "案2", "案3"]
