"""SpanPatchApplier の安全条件の回帰テスト。"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.prose.span_patch_applier import SpanPatchApplier


def test_happy_path_replaces_span():
    ap = SpanPatchApplier()
    out, ok = ap.apply("AAAABBBBCCCC", 4, 8, "ZZZZZZZZ")
    assert ok is True and out == "AAAAZZZZZZZZCCCC"


def test_rejects_out_of_range():
    ap = SpanPatchApplier()
    assert ap.apply("AAAA", 2, 99, "ZZZZZZZZ")[1] is False
    assert ap.apply("AAAA", 2, 2, "ZZZZZZZZ")[1] is False
    assert ap.apply("AAAA", -1, 3, "ZZZZZZZZ")[1] is False


def test_rejects_empty_replacement():
    ap = SpanPatchApplier()
    assert ap.apply("AAAABBBB", 4, 8, "   ")[1] is False


def test_rejects_catastrophic_shrink():
    ap = SpanPatchApplier()
    assert ap.apply("A" * 100, 0, 100, "B")[1] is False


def test_rejects_paragraph_loss():
    ap = SpanPatchApplier()
    text = "p1\n\np2\n\np3"
    out, ok = ap.apply(text, 0, len(text), "merged")
    assert ok is False and out == text


def test_single_paragraph_replacement_is_accepted():
    """段落を潰さない範囲の差し替えは通ること（安全条件4つだけを判定する）。"""
    ap = SpanPatchApplier()
    text = "p1\n\np2\n\np3"
    out, ok = ap.apply(text, 0, len("p1"), "merged")
    assert ok is True and out == "merged\n\np2\n\np3"


def test_never_raises_on_garbage():
    ap = SpanPatchApplier()
    assert ap.apply("", 0, 0, "x")[1] is False
    assert ap.apply(None, 0, 1, "x")[1] is False
