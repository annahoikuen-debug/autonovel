"""H8: `src/audit/span_revision.py` (QuotePatch / apply_quote_patches) の単体テスト。

LLM を 1 回も使わず、純粋な置換・検証ロジックを検証する。
回帰の核心：「原文は一切破壊されない」「検証不通は rejected へ回収」。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.audit.span_revision import QuotePatch, apply_quote_patches, find_quote_span


class TestFindQuoteSpan:
    def test_exact_match_returns_span(self):
        text = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"
        span = find_quote_span(text, "古代の魔導書", max_quote_chars=400)
        assert span == (17, 23), span
        assert text[span[0] : span[1]] == "古代の魔導書"

    def test_quote_not_found_returns_none(self):
        assert find_quote_span("AAAA BBBB", "CCCC", max_quote_chars=400) is None

    def test_empty_quote_returns_none(self):
        assert find_quote_span("AAAA", "", max_quote_chars=400) is None
        assert find_quote_span("AAAA", "   ", max_quote_chars=400) is None

    def test_quote_over_max_chars_returns_none(self):
        long_q = "A" * 401
        assert find_quote_span("AAAA", long_q, max_quote_chars=400) is None

    def test_whitespace_normalized_match(self):
        # 空白の量が異なるだけ（有無は同じ）なら正規化後一致でヒット
        text = "その名を  古代の魔導書と書く。"  # スペース 2 個
        quote = "その名を 古代の魔導書と書く。"  # スペース 1 個
        span = find_quote_span(text, quote, max_quote_chars=400)
        assert span is not None, span
        assert text[span[0] : span[1]] == "その名を  古代の魔導書と書く。"

    def test_first_occurrence_only(self):
        text = "AAAA BBBB AAAA CCCC"
        span = find_quote_span(text, "AAAA", max_quote_chars=400)
        assert span == (0, 4)

    def test_quote_at_end_of_text(self):
        text = "本文の最後はここで終わり。"
        span = find_quote_span(text, "ここで終わり。", max_quote_chars=400)
        assert span == (6, 13), span
        assert text[span[0] : span[1]] == "ここで終わり。"


class TestApplyQuotePatches:
    def test_happy_path_replaces(self):
        text = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"
        patches = [QuotePatch(original_quote="古代の魔導書", replacement="古代の魔道書", rationale="表記揺れ修正")]
        result = apply_quote_patches(text, patches)
        assert result.applied_count == 1
        assert result.rejected == ()
        assert "古代の魔道書" in result.text
        assert "古代の魔導書" not in result.text
        # 残りの本文はそのまま
        assert result.text.startswith("主人公は立ち止まった。")
        assert result.text.endswith("夜が明けた。")

    def test_multiple_patches_applied_in_order(self):
        text = "A\n\nB\n\nC"
        patches = [
            QuotePatch(original_quote="A", replacement="A'"),
            QuotePatch(original_quote="C", replacement="C'"),
        ]
        result = apply_quote_patches(text, patches, max_patches=10)
        assert result.applied_count == 2
        assert result.text == "A'\n\nB\n\nC'"

    def test_not_found_goes_to_rejected_original_unchanged(self):
        text = "AAAA BBBB"
        patches = [QuotePatch(original_quote="CCCC", replacement="CCCC'")]
        result = apply_quote_patches(text, patches)
        assert result.applied_count == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].original_quote == "CCCC"
        assert result.text == text

    def test_empty_quote_goes_to_rejected(self):
        text = "AAAA BBBB"
        patches = [QuotePatch(original_quote="", replacement="X")]
        result = apply_quote_patches(text, patches)
        assert result.applied_count == 0
        assert result.text == text

    def test_quote_over_400_chars_goes_to_rejected(self):
        text = "AAAA BBBB"
        long_q = "Q" * 401
        patches = [QuotePatch(original_quote=long_q, replacement="X")]
        result = apply_quote_patches(text, patches)
        assert result.applied_count == 0
        assert result.text == text

    def test_max_patches_limits_applications(self):
        text = "A\n\nA\n\nA\n\nA"
        patches = [QuotePatch(original_quote="A", replacement="X")] * 4
        result = apply_quote_patches(text, patches, max_patches=2)
        assert result.applied_count == 2
        assert len(result.rejected) == 2

    def test_validation_rejects_catastrophic_shrink(self):
        # 本文のほぼ全部を 1 字に縮める -> 長さ比 0.3 未満で不採用
        text = "A" * 100
        patches = [QuotePatch(original_quote="A" * 100, replacement="X")]
        result = apply_quote_patches(text, patches)
        assert result.applied_count == 0
        assert len(result.rejected) == 1
        assert result.text == text

    def test_validation_rejects_paragraph_loss(self):
        text = "p1\n\np2\n\np3"
        # 全文を 1 段落に置き換えると段落数が減る -> 不採用
        patches = [QuotePatch(original_quote=text, replacement="merged")]
        result = apply_quote_patches(text, patches)
        assert result.applied_count == 0
        assert result.text == text

    def test_original_text_never_mutated(self):
        text = "AAAA BBBB"
        original = text
        apply_quote_patches(text, [QuotePatch(original_quote="AAAA", replacement="XXXX")])
        assert text == original  # str は不変だが、副作用なしを明示

    def test_replacement_empty_string_rejected(self):
        text = "AAAA BBBB"
        patches = [QuotePatch(original_quote="AAAA", replacement="   ")]
        result = apply_quote_patches(text, patches)
        assert result.applied_count == 0
        assert result.text == text

    def test_non_string_text_returns_empty(self):
        result = apply_quote_patches(None, [])  # type: ignore[arg-type]
        assert result.text == ""
        assert result.applied_count == 0


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
