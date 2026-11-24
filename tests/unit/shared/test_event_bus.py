"""src/shared/event_bus.py (UIEventType) の単体テスト."""

from __future__ import annotations

from src.shared.event_bus import UIEventType


class TestUIEventType:
    """UIEventType 列挙体のテスト."""

    def test_request_generate_plan(self):
        assert UIEventType.REQUEST_GENERATE_PLAN == "REQUEST_GENERATE_PLAN"
        assert isinstance(UIEventType.REQUEST_GENERATE_PLAN, str)

    def test_request_audit_plan(self):
        assert UIEventType.REQUEST_AUDIT_PLAN == "REQUEST_AUDIT_PLAN"

    def test_request_generate_episode(self):
        assert UIEventType.REQUEST_GENERATE_EPISODE == "REQUEST_GENERATE_EPISODE"

    def test_request_cancel_job(self):
        assert UIEventType.REQUEST_CANCEL_JOB == "REQUEST_CANCEL_JOB"

    def test_all_values_unique(self):
        values = [e.value for e in UIEventType]
        assert len(values) == len(set(values))

    def test_str_enum_behavior(self):
        # StrEnum なので str と比較可能
        assert UIEventType.REQUEST_GENERATE_PLAN == "REQUEST_GENERATE_PLAN"
        assert UIEventType("REQUEST_CANCEL_JOB") == UIEventType.REQUEST_CANCEL_JOB
