"""Unit tests for src/domain/writing/jit_expander.py (JIT Beat Expander).

Pure-logic coverage: metrics calculation (char count, dialogue ratio, ruby),
and editor/beat synchronization.
"""
from __future__ import annotations

import pytest

from src.domain.writing.jit_expander import EditorMetrics, JITBeatExpander


class TestEditorMetrics:
    def test_defaults_are_zero(self):
        m = EditorMetrics()
        assert m.char_count == 0
        assert m.dialogue_char_count == 0
        assert m.dialogue_ratio == 0.0
        assert m.ruby_count == 0


class TestCalculateMetrics:
    def test_empty_text_returns_defaults(self):
        m = JITBeatExpander.calculate_metrics("")
        assert isinstance(m, EditorMetrics)
        assert m.char_count == 0
        assert m.dialogue_char_count == 0
        assert m.dialogue_ratio == 0.0
        assert m.ruby_count == 0

    def test_none_text_returns_defaults(self):
        m = JITBeatExpander.calculate_metrics(None)
        assert m.char_count == 0

    def test_plain_text_no_dialogue(self):
        m = JITBeatExpander.calculate_metrics("hello world")
        assert m.char_count == 11
        assert m.dialogue_char_count == 0
        assert m.dialogue_ratio == 0.0
        assert m.ruby_count == 0

    def test_dialogue_ratio_extraction(self):
        text = "前日譚「こんにちは」後日譭「さようなら」"
        m = JITBeatExpander.calculate_metrics(text)
        # 「こんにちは」(5) + 「さようなら」(5) = 10 dialogue chars
        assert m.dialogue_char_count == 10
        clean = text.replace("\r", "")
        assert m.dialogue_ratio == round(10 / len(clean), 3)

    def test_empty_dialogue_brackets_count_as_zero(self):
        m = JITBeatExpander.calculate_metrics("「」")
        assert m.dialogue_char_count == 0
        assert m.dialogue_ratio == 0.0

    def test_ruby_count(self):
        # ruby pattern requires a leading ``|``: ``|漢字《ルビ》``
        text = "|漢字《ルビ》|かな《あ》"
        m = JITBeatExpander.calculate_metrics(text)
        assert m.ruby_count == 2

    def test_crlf_is_stripped(self):
        text = "hello\r\nworld"
        # only ``\r`` is stripped; ``\n`` remains
        m = JITBeatExpander.calculate_metrics(text)
        assert m.char_count == len(text.replace("\r", ""))

    def test_ratio_zero_when_only_dialogue_brackets_and_zero_chars(self):
        # dialogue chars exist but total char_count is 0 cannot happen, but
        # exercise the guard for char_count == 0 with an empty-ish edge.
        m = JITBeatExpander.calculate_metrics("")
        assert m.dialogue_ratio == 0.0


class TestSyncEditorContentWithBeats:
    def test_empty_beats_uses_single_total(self):
        result = JITBeatExpander.sync_editor_content_with_beats("abc", [])
        assert result["is_synchronized"] is True
        assert result["updated_beats"] == []
        assert result["metrics"]["char_count"] == 3

    def test_multiple_beats_allocates_evenly(self):
        text = "abcdefgh"  # 8 chars
        beats = [{"id": 1}, {"id": 2}]
        result = JITBeatExpander.sync_editor_content_with_beats(text, beats)
        allocated = 8 // 2
        assert result["updated_beats"][0]["current_chars"] == allocated
        assert result["updated_beats"][0]["completed"] is True  # 8 >= 1*4
        assert result["updated_beats"][1]["completed"] is True  # 8 >= 2*4

    def test_allocation_zero_uses_guard(self):
        # char_count smaller than number of beats -> allocated_target 0
        text = "ab"  # 2 chars
        beats = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = JITBeatExpander.sync_editor_content_with_beats(text, beats)
        # 2 // 3 == 0, so `allocated_target or 1` -> 1
        assert result["updated_beats"][0]["current_chars"] == 0
        assert result["updated_beats"][0]["completed"] is True  # 2 >= 1*1
        # 2 >= 2*1 -> True
        assert result["updated_beats"][1]["completed"] is True
        # 2 >= 3*1 -> False
        assert result["updated_beats"][2]["completed"] is False

    def test_beat_dict_is_not_mutated(self):
        original = {"id": 1, "note": "x"}
        result = JITBeatExpander.sync_editor_content_with_beats("hello", [original])
        assert original == {"id": 1, "note": "x"}
        assert result["updated_beats"][0]["note"] == "x"
