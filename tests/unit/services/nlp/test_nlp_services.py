"""services/nlp: 日本語トークナイザ・述語スコアラ・時制解析・伏線述語解析。"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from src.models.predicate_match import PredicateAnalysisResult, PredicateMatch
from src.services.nlp.foreshadowing_predicate_analyzer import (
    ForeshadowingPredicateAnalyzer,
)
from src.services.nlp.japanese_tokenizer import NOVEL_STOPWORDS, JapaneseTokenizer
from src.services.nlp.predicate_scorer import PredicateScorer
from src.services.nlp.tense_analyzer import TenseAnalyzer, TenseContextAnalyzer


# --------------------------------------------------------------------------
# japanese_tokenizer.py (regex fallback: sudachipy is an optional extra)
# --------------------------------------------------------------------------
def test_tokenizer_fallback_basics():
    t = JapaneseTokenizer()
    t._sudachi_tokenizer = None  # force regex fallback path
    assert t.is_sudachi_available is False
    assert t.normalize_text("  Ａ  ") == "A"
    assert t.normalize_text(None) == ""
    assert t.tokenize("") == []
    assert t.tokenize("主人公が剣を振った") == ["主人公", "剣", "振", "った"]


def test_tokenizer_filters_stopwords_and_min_len():
    t = JapaneseTokenizer(stopwords={"主人公"}, min_len=2)
    assert "主人公" not in t.tokenize("主人公 が 剣")
    assert t.tokenize("a") == []


def test_tokenizer_regex_branches():
    t = JapaneseTokenizer(stopwords=set())
    t._sudachi_tokenizer = None
    out = t.tokenize("Ｔｅｓｔ カタカナ かなカナ 123 々々")
    assert "Test" in out
    assert "カタカナ" in out
    assert any(w.isdigit() for w in out)


class _Morph:
    def __init__(self, pos, normalized, surface, dict_form=None):
        self._pos = pos
        self._normalized = normalized
        self._surface = surface
        self._dict_form = dict_form or surface

    def part_of_speech(self):
        return self._pos

    def normalized_form(self):
        return self._normalized

    def surface(self):
        return self._surface

    def dictionary_form(self):
        return self._dict_form


class _FakeSudachi:
    def __init__(self, morphemes=None, raise_on_call=False):
        self._morphemes = morphemes or []
        self.raise_on_call = raise_on_call
        self.last_args = None

    def tokenize(self, text, mode=None):
        self.last_args = (text, mode)
        if self.raise_on_call:
            raise RuntimeError("sudachi boom")
        return self._morphemes


def test_tokenizer_sudachi_path():
    t = JapaneseTokenizer(stopwords={"主人公"})
    fake = _FakeSudachi([
        _Morph(("名詞", "一般"), "主人公", "主人公"),
        _Morph(("名詞", "固有名詞"), "剣", "剣"),
        _Morph(("動詞", "非自立"), "する", "する"),
        _Morph(("助詞",), "を", "を"),
        _Morph(("形容詞",), "静か", "静か"),
        _Morph(("動詞",), "揺れる", "揺れる", dict_form="揺れる"),
    ])
    t._sudachi_tokenizer = fake
    assert t.is_sudachi_available is True
    t._split_mode = "MODE"
    out = t.tokenize("主人公が剣を振り、静かだった")
    assert "主人公" not in out
    assert "剣" in out
    assert "する" not in out
    assert "を" not in out
    assert "静か" in out
    assert "揺れる" in out
    assert fake.last_args[1] == "MODE"


def test_tokenizer_sudachi_surface_form_and_min_len():
    t = JapaneseTokenizer(use_normalized_form=False, min_len=2, stopwords=set())
    t._sudachi_tokenizer = _FakeSudachi([
        _Morph(("名詞",), "あいうえお", "短"),
        _Morph(("名詞",), "xyz", " longsuf "),
    ])
    out = t.tokenize("hoge")
    assert "あいうえお" not in out
    assert "短" not in out
    assert "longsuf" in out

    t2 = JapaneseTokenizer(use_normalized_form=True, min_len=1, stopwords=set())
    t2._sudachi_tokenizer = _FakeSudachi([_Morph(("名詞",), "あいうえお", "短")])
    assert t2.tokenize("hoge") == ["あいうえお"]


def test_tokenizer_sudachi_error_falls_back():
    t = JapaneseTokenizer()
    t._sudachi_tokenizer = _FakeSudachi(raise_on_call=True)
    assert t.tokenize("主人公") == ["主人公"]


def test_tokenizer_init_sudachi_succeeds(monkeypatch):
    class Dict:
        def create(self):
            return _FakeSudachi([_Morph(("名詞",), "x", "x")])

    fake = types.ModuleType("sudachipy")
    fake.dictionary = types.SimpleNamespace(Dictionary=Dict)
    fake.tokenizer = types.SimpleNamespace(
        Tokenizer=type("T", (), {"SplitMode": types.SimpleNamespace(A=1, B=2, C=3)})
    )
    monkeypatch.setitem(sys.modules, "sudachipy", fake)

    for mode, expected in (("A", 1), ("B", 2), ("c", 3), ("Z", 3)):
        t = JapaneseTokenizer(split_mode=mode)
        assert t._split_mode == expected
        assert t.is_sudachi_available is True


def test_tokenizer_custom_pos_and_stopwords():
    t = JapaneseTokenizer(allowed_pos={"動詞"}, excluded_sub_pos=set(), stopwords={"x"})
    assert t.allowed_pos == {"動詞"}
    assert t.stopwords == {"x"}
    assert "これ" in NOVEL_STOPWORDS


# --------------------------------------------------------------------------
# predicate_scorer.py
# --------------------------------------------------------------------------
def _match(ptype, conf=1.0, sentence="解決した。"):
    return PredicateMatch(
        keyword="k", predicate="p", predicate_type=ptype, sentence=sentence,
        confidence_score=conf,
    )


def test_predicate_scorer_no_matches():
    assert PredicateScorer.calculate_score(PredicateAnalysisResult(foreshadowing_id=1)) == 0


def test_predicate_scorer_all_negated():
    r = PredicateAnalysisResult(
        foreshadowing_id=1,
        matches=[
            _match("resolved", sentence="真破人はいらない。" "それは未来ではない。"),
            _match("progressed", sentence="真破人はいらない。" "それは未来ではない。"),
        ],
    )
    assert PredicateScorer.calculate_score(r) == 0


def test_predicate_scorer_resolved_scaled():
    r = PredicateAnalysisResult(foreshadowing_id=1, matches=[_match("resolved", 0.8)])
    assert PredicateScorer.calculate_score(r) == 20


def test_predicate_scorer_progressed_scaled():
    r = PredicateAnalysisResult(foreshadowing_id=1, matches=[_match("progressed", 0.6)])
    assert PredicateScorer.calculate_score(r) == 9


def test_predicate_scorer_mention_and_mixed():
    r = PredicateAnalysisResult(foreshadowing_id=1, matches=[_match("mention_only")])
    assert PredicateScorer.calculate_score(r) == 5
    r2 = PredicateAnalysisResult(
        foreshadowing_id=1, matches=[_match("mention_only"), _match("resolved", 1.0)]
    )
    assert PredicateScorer.calculate_score(r2) == 25


def test_predicate_scorer_unknown_only():
    r = PredicateAnalysisResult(foreshadowing_id=1, matches=[_match("unknown")])
    assert PredicateScorer.calculate_score(r) == 0


# --------------------------------------------------------------------------
# tense_analyzer.py
# --------------------------------------------------------------------------
def test_tense_sentence_classification():
    a = TenseContextAnalyzer()
    assert a.analyze_sentence_tense("  ") == "NEUTRAL"
    assert a.analyze_sentence_tense("「おはよう」") == "DIALOGUE"
    assert a.analyze_sentence_tense("『ふむ』") == "DIALOGUE"
    assert a.analyze_sentence_tense("ただの体言止め") == "OTHER"
    assert a.analyze_sentence_tense("彼は走った。") == "PAST"
    assert a.analyze_sentence_tense("彼は走る。") == "PRESENT"
    assert a.analyze_sentence_tense("彼は奇。") == "OTHER"


def test_tense_paragraph_results():
    a = TenseContextAnalyzer()
    empty = a.analyze_paragraph("   ")
    assert empty.dominant_tense == "NEUTRAL"
    assert empty.sentence_tenses == []

    neutral = a.analyze_paragraph("「はい」。ただの行。")
    assert neutral.dominant_tense == "NEUTRAL"
    assert neutral.sentence_tenses == ["DIALOGUE", "OTHER"]

    past = a.analyze_paragraph("彼は走った。彼女は待った。空は静まった。")
    assert past.dominant_tense == "PAST"
    assert past.is_past_locked is True
    assert past.past_ratio == 1.0

    present = a.analyze_paragraph("彼は走る。彼女は待つ。空は静まる。")
    assert present.dominant_tense == "PRESENT"
    assert present.present_ratio == 1.0

    mixed = a.analyze_paragraph("彼は走った。彼は走る。空は静かだ。")
    assert mixed.dominant_tense == "MIXED"
    assert mixed.is_past_locked is False


def test_tense_analyzer_facade():
    out = TenseAnalyzer().analyze("彼は走った。")
    assert set(out) == {"past_ratio", "present_ratio"}
    assert out["past_ratio"] == 1.0


# --------------------------------------------------------------------------
# foreshadowing_predicate_analyzer.py
# --------------------------------------------------------------------------
def test_predicate_analyzer_split_sentences():
    a = ForeshadowingPredicateAnalyzer()
    assert a.split_sentences("") == []
    out = a.split_sentences("これは事実だ。次に炒飯！\nそして終わり？")
    assert out == ["これは事実だ。", "次に炒飯！", "そして終わり？"]


def test_predicate_analyzer_resolved_match():
    a = ForeshadowingPredicateAnalyzer()
    res = a.analyze_sentence("彼は敵を見破った。", "敵")
    assert ("見破る", "resolved") in res


def test_predicate_analyzer_mention_match():
    a = ForeshadowingPredicateAnalyzer()
    res = a.analyze_sentence("彼は刀を持った。", "刀")
    assert ("持つ", "mention_only") in res


def test_predicate_analyzer_stem_variants():
    a = ForeshadowingPredicateAnalyzer()
    cases = {
        "真犯人が明らかになった。": "明らかになる",
        "事実は判明した。": "判明する",
        "oisyn": None,
        "伏線は回収された。": "回収される",
        "何かが視界を遮る？": None,
    }
    found = {}
    for sentence, expected in cases.items():
        res = a.analyze_sentence(sentence, "kw")
        found[sentence] = res
        if expected is not None:
            assert (expected, "resolved") in res, sentence
    assert found["oisyn"] == []
    assert isinstance(found["何かが視界を遮る？"], list)


def test_predicate_analyzer_sudachi_path():
    a = ForeshadowingPredicateAnalyzer()
    a._tokenizer = _FakeSudachi([
        _Morph(("名詞",), "事件", "事件"),
        _Morph(("動詞",), "解明", "解明", dict_form="解明する"),
        _Morph(("形容詞", "非自立"), "x", "x"),
        _Morph(("動詞",), "見る", "見る", dict_form="見る"),
    ])
    a._split_mode = "C"
    res = a.analyze_sentence("事件が解明された。", "事件")
    assert ("事件解明する", "unknown") in res
    assert ("見る", "mention_only") in res


def test_predicate_analyzer_sudachi_error():
    a = ForeshadowingPredicateAnalyzer()
    a._tokenizer = _FakeSudachi(raise_on_call=True)
    assert a.analyze_sentence("何も", "kw") == []


def test_predicate_analyzer_foreshadowing_levels():
    a = ForeshadowingPredicateAnalyzer()
    none = a.analyze_foreshadowing(1, ["kw"], "まったく無関係な文章。")
    assert none.highest_action == "none"
    assert none.syntax_score == 0

    mention = a.analyze_foreshadowing(1, ["剣"], "彼は剣を手に取った。")
    assert mention.highest_action == "mention_only"
    assert mention.syntax_score == 5
    assert mention.matches

    resolved = a.analyze_foreshadowing(2, ["敵"], "彼は敵を見破った。")
    assert resolved.highest_action == "resolved"
    assert resolved.syntax_score == 25
    has_tokenizer = a._tokenizer is not None
    assert all(
        m.confidence_score == (0.9 if has_tokenizer else (0.85 if m.predicate_type == "resolved" else 0.7))
        for m in resolved.matches
    )

    no_tok = ForeshadowingPredicateAnalyzer()
    no_tok._tokenizer = None
    r2 = no_tok.analyze_foreshadowing(2, ["真犯人"], "真犯人が明らかになった。")
    assert r2.highest_action == "resolved"
    assert r2.matches[0].confidence_score == 0.85
    r3 = no_tok.analyze_foreshadowing(3, ["剣"], "彼は剣を持っている。")
    assert r3.highest_action == "mention_only"
    assert all(m.confidence_score == 0.7 for m in r3.matches)

    progressed = a.analyze_foreshadowing(3, ["音"], "その音に気づいた。")
    assert progressed.highest_action == "progressed"
    assert progressed.syntax_score == 15


def test_predicate_analyzer_sudachi_available_confidence():
    a = ForeshadowingPredicateAnalyzer()
    a._tokenizer = _FakeSudachi([_Morph(("動詞",), "見る", "見る", dict_form="見る")])
    res = a.analyze_foreshadowing(1, ["剣"], "剣を見る。")
    assert res.matches
    assert res.matches[0].confidence_score == 0.9
