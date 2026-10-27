"""Tests for src/services/cadence compound merger, span extractor and models."""
from __future__ import annotations

import pytest

from src.services.cadence.compound_merger import CompoundSentenceMerger
from src.services.cadence.models import (
    CadenceIntelligentConfig,
    CadenceMode,
)
from src.services.cadence.span_extractor import (
    TargetSpan,
    ViolationSpanExtractor,
)


class TestConvertToConjunctive:
    @pytest.mark.parametrize(
        "sentence,expected",
        [
            ("彼は走っていた。", "彼は走っており、"),
            ("彼女は話していた。", "彼女は話しており、"),
            ("それは夢だった。", "それは夢であり、"),
            ("静かであった。", "静かであって、"),
            ("彼は書いた。", "彼は書き、"),
            ("彼は怒った。", "彼は怒り、"),
            ("彼は跳んだ。", "彼は跳み、"),
            ("彼は読んだ。", "彼は読み、"),
            ("彼は伝えた。", "彼は伝え、"),
            ("彼は抜けた。", "彼は抜け、"),
            ("彼は止めた。", "彼は止め、"),
            ("彼は溺れた。", "彼は溺れ、"),
            ("見た。", None),
            ("逃げた。", None),
            ("Outside。", None),
        ],
    )
    def test_conversions(self, sentence, expected):
        merger = CompoundSentenceMerger()
        if expected is None:
            assert merger.convert_to_conjunctive(sentence) is None
        else:
            assert merger.convert_to_conjunctive(sentence) == expected

    def test_unconvertible_ending(self):
        merger = CompoundSentenceMerger()
        assert merger.convert_to_conjunctive("走った。") == "走り、"
        assert merger.convert_to_conjunctive("名词") is None


class TestCanMerge:
    def test_basic_ok(self):
        merger = CompoundSentenceMerger()
        assert merger.can_merge("彼は走った。", "早かった。") is True

    def test_empty(self):
        merger = CompoundSentenceMerger()
        assert merger.can_merge("", "早かった。") is False
        assert merger.can_merge("走った。", "   ") is False

    def test_dialogue_protected(self):
        merger = CompoundSentenceMerger()
        assert merger.can_merge("「行こう」。", "早かった。") is False
        assert merger.can_merge("『行こう』。", "早かった。") is False
        assert merger.can_merge("走った。", "「行こう」。") is False
        assert merger.can_merge("走った。「行こう」。", "早かった。") is False

    def test_exclamation_protected(self):
        merger = CompoundSentenceMerger()
        assert merger.can_merge("走った！", "早かった。") is False
        assert merger.can_merge("走った?", "早かった。") is False
        assert merger.can_merge("走った。", "早い？") is False

    def test_too_long(self):
        merger = CompoundSentenceMerger()
        assert merger.can_merge("あ" * 50 + "。", "い" * 50 + "。") is False
        assert merger.can_merge("あ" * 50 + "。", "い" * 50 + "。", max_chars=200) is True

    def test_too_short(self):
        merger = CompoundSentenceMerger()
        assert merger.can_merge("だ。", "早かった。") is False
        assert merger.can_merge("走った。", "だ。") is False

    def test_uses_instance_default_limit(self):
        merger = CompoundSentenceMerger(max_chars=10)
        assert merger.can_merge("走った。", "早い。") is False


class TestMergeSentences:
    def test_merges(self):
        merger = CompoundSentenceMerger()
        assert merger.merge_sentences("彼は走った。", "早かった。") == "彼は走り、早かった。"

    def test_returns_none_when_unmergeable(self):
        merger = CompoundSentenceMerger()
        assert merger.merge_sentences("彼は走った。", "だ。") is None
        assert merger.merge_sentences("早晨。", "早かった。") is None

    def test_respects_max_chars_arg(self):
        merger = CompoundSentenceMerger()
        assert merger.merge_sentences("走った。", "早かった。", max_chars=4) is None


class TestReduceConsecutiveEndings:
    def test_single_sentence(self):
        merger = CompoundSentenceMerger()
        assert merger.reduce_consecutive_endings(["走った。"]) == (["走った。"], 0)
        assert merger.reduce_consecutive_endings([]) == ([], 0)

    def test_merges_run_of_ta(self):
        merger = CompoundSentenceMerger()
        sents = ["彼は走った。", "彼は跳んだ。", "彼は見た。", "彼は笑った。"]
        out, count = merger.reduce_consecutive_endings(sents, max_consecutive=2)
        assert count == 1
        assert out == ["彼は走った。", "彼は跳み、彼は見た。", "彼は笑った。"]

    def test_multiple_merges(self):
        merger = CompoundSentenceMerger()
        sents = ["彼は走った。", "彼は跳んだ。", "彼は見た。", "彼は笑った。", "彼は泣いた。", "彼は怒った。"]
        out, count = merger.reduce_consecutive_endings(sents, max_consecutive=2)
        assert count == 2
        assert len(out) == 4

    def test_skips_empty_strings(self):
        merger = CompoundSentenceMerger()
        sents = ["彼は走った。", "  ", "彼は跳んだ。", "彼は見た。", "彼は笑った。"]
        out, count = merger.reduce_consecutive_endings(sents, max_consecutive=2)
        assert "  " not in out
        assert count == 1

    def test_no_merge_when_threshold_not_met(self):
        merger = CompoundSentenceMerger()
        sents = ["彼は走った。", "彼は跳んだ。", "彼は見た。", "彼は笑った。"]
        out, count = merger.reduce_consecutive_endings(sents, max_consecutive=5)
        assert count == 0
        assert out == [s.strip() for s in sents]

    def test_no_merge_when_merged_text_too_long(self):
        merger = CompoundSentenceMerger()
        sents = ["彼は走った。", "彼は跳んだ。", "彼は見た。", "彼は笑った。", "彼は泣いた。", "彼は怒った。"]
        out, count = merger.reduce_consecutive_endings(sents, max_consecutive=2, max_chars=5)
        assert count == 0
        assert out == sents

    def test_trailing_run_without_next(self):
        merger = CompoundSentenceMerger()
        out, count = merger.reduce_consecutive_endings(
            ["彼は走った。", "彼は跳んだ。", "彼は見た。"], max_consecutive=2
        )
        assert count == 1


class TestTargetSpan:
    def test_target_text(self):
        span = TargetSpan(0, 1, ["a。", "b。"])
        assert span.target_text == "a。b。"
        assert span.violation_type == "consecutive_ta"

    def test_window_text_with_context(self):
        span = TargetSpan(1, 2, ["b。", "c。"], preceding_context="a。", following_context="d。")
        text = span.window_text
        assert "[直前文脈]: a。" in text
        assert "[改善対象]: b。c。" in text
        assert "[直後文脈]: d。" in text

    def test_window_text_no_context(self):
        span = TargetSpan(0, 0, ["a。"])
        assert span.window_text == "[改善対象]: a。"


class TestViolationSpanExtractor:
    def test_too_few_sentences(self):
        extractor = ViolationSpanExtractor(max_consecutive=3)
        assert extractor.extract_spans(["走った。", "跳んだ。"]) == []

    def test_extracts_violation(self):
        extractor = ViolationSpanExtractor(max_consecutive=3)
        sents = ["前文。", "走った。", "跳んだ。", "見た。", "後文。"]
        spans = extractor.extract_spans(sents)
        assert len(spans) == 1
        assert spans[0].start_sentence_idx == 1
        assert spans[0].end_sentence_idx == 3
        assert spans[0].preceding_context == "前文。"
        assert spans[0].following_context == "後文。"

    def test_violation_at_start(self):
        extractor = ViolationSpanExtractor(max_consecutive=2)
        spans = extractor.extract_spans(["走った。", "跳んだ。", "違う。"])
        assert spans[0].preceding_context == ""
        assert spans[0].following_context == "違う。"

    def test_violation_at_end(self):
        extractor = ViolationSpanExtractor(max_consecutive=2)
        spans = extractor.extract_spans(["違う。", "走った。", "跳んだ。"])
        assert spans[0].following_context == ""

    def test_quotes_and_blank_break_run(self):
        extractor = ViolationSpanExtractor(max_consecutive=2)
        assert extractor.extract_spans(["走った。", "「 Quotes」".strip(), "跳んだ。"]) == []
        assert extractor.extract_spans(["走った。", "  ", "跳んだ。"]) == []

    def test_non_ta_breaks_run(self):
        extractor = ViolationSpanExtractor(max_consecutive=2)
        assert extractor.extract_spans(["走った。", "走っている。", "跳んだ。"]) == []

    def test_two_spans(self):
        extractor = ViolationSpanExtractor(max_consecutive=2)
        sents = ["走った。", "跳んだ。", "違う。", "見た。", "笑った。"]
        assert len(extractor.extract_spans(sents)) == 2

    def test_splice_replaces_span(self):
        extractor = ViolationSpanExtractor(max_consecutive=2)
        sents = ["違う。", "走った。", "跳んだ。", "後ろ。"]
        span = TargetSpan(1, 2, sents[1:3])
        out = extractor.splice_span(sents, span, "新文A。新文B。")
        assert out == ["違う。", "新文A。", "新文B。", "後ろ。"]

    def test_splice_empty_refined_returns_original(self):
        extractor = ViolationSpanExtractor()
        sents = ["a。"]
        assert extractor.splice_span(sents, TargetSpan(0, 0, ["a。"]), "   ") is sents

    def test_splice_without_punctuation(self):
        extractor = ViolationSpanExtractor()
        sents = ["a。", "b。"]
        span = TargetSpan(0, 0, ["a。"])
        out = extractor.splice_span(sents, span, "no punctuation here")
        assert out == ["no punctuation here", "b。"]


class TestCadenceConfig:
    def test_defaults(self):
        cfg = CadenceIntelligentConfig()
        assert cfg.mode == CadenceMode.HYBRID
        assert cfg.max_consecutive_ta == 3
        assert cfg.enable_llm_refine is True
        assert cfg.llm_model_name == "gemini-1.5-flash"

    def test_validation_bounds(self):
        with pytest.raises(Exception):
            CadenceIntelligentConfig(max_consecutive_ta=1)
        with pytest.raises(Exception):
            CadenceIntelligentConfig(llm_temperature=5.0)
        with pytest.raises(Exception):
            CadenceIntelligentConfig(max_compound_chars=10)

    def test_extra_ignored(self):
        cfg = CadenceIntelligentConfig(unknown_field="x")
        assert not hasattr(cfg, "unknown_field")

    def test_mode_values(self):
        assert {m.value for m in CadenceMode} == {
            "rule_safe",
            "compound_merge",
            "local_llm",
            "hybrid",
        }
