"""
改善案4: タグ配線の契約テスト。

フラグ ENABLE_TAG_WIRING が OFF の間は、現行挙動とバイト同一を維持する。
"""

from __future__ import annotations

from src.domain.entities.easy_mode import GenerationResponse


class TestTagContractFlagOff:
    """フラグOFF時の契約テスト。"""

    def test_generation_response_has_optional_tag_field(self):
        # GenerationResponse に tag_suggestions が default_factory=list で
        # 追加されており、未指定でもインスタンス化できること（後方互換）
        resp = GenerationResponse(task_id="task-123", output="本文")
        assert resp.tag_suggestions == []
        # 既存フィールドの契約も維持
        assert resp.hook_metrics is None
        assert resp.ctr_metrics is None
        assert resp.ctr_suggestions == []

    def test_generation_response_can_set_tag_field(self):
        resp = GenerationResponse(
            task_id="task-123",
            output="本文",
            tag_suggestions=["異世界転生", "チート"],
        )
        assert resp.tag_suggestions == ["異世界転生", "チート"]
