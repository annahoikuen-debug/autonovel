"""ParagraphIndexer が文字オフセットを返すことの回帰テスト。"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.prose.paragraph_indexer import ParagraphIndexer


def test_offsets_point_at_actual_text():
    text = "第一段落。\n\n第二段落の本文。\n\n第三段落。"
    out = ParagraphIndexer().index_paragraphs(text)
    assert len(out) == 3
    for item in out:
        assert text[item["start"]:item["end"]] == item["text"], item


def test_legacy_keys_still_present():
    out = ParagraphIndexer().index_paragraphs("あ。\n\nい。")
    assert set(out[0]) >= {"index", "text", "start", "end"}
    assert [i["index"] for i in out] == [0, 1]


def test_leading_whitespace_does_not_shift_offsets():
    text = "\n\nあいうえお。\n\nかきくけこ。"
    out = ParagraphIndexer().index_paragraphs(text)
    assert text[out[0]["start"]:out[0]["end"]] == "あいうえお。"


def test_empty_text_returns_empty_list():
    assert ParagraphIndexer().index_paragraphs("   \n\n  ") == []
