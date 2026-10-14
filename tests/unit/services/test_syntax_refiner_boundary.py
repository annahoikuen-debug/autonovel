import pytest
from src.services.anti_ai.syntax_refiner import SyntaxRefiner


@pytest.fixture
def refiner():
    return SyntaxRefiner()


def test_filler_removal_at_sentence_start(refiner):
    """文頭のフィラーが確実に除去されること。"""
    text = "たぶん、彼は成功するだろう。"
    refined, _, _ = refiner.refine_paragraph(text)
    assert "たぶん" not in refined


def test_filler_removal_after_comma(refiner):
    """読点直後のフィラーが確実に除去されること。"""
    text = "彼は、おそらく道に迷った。"
    refined, _, _ = refiner.refine_paragraph(text)
    assert "おそらく" not in refined


def test_filler_removal_in_dialogue(refiner):
    """会話文の鍵括弧直後のフィラーも除去されること。"""
    text = "「きっと、明日は晴れる」と彼女は言った。"
    refined, _, _ = refiner.refine_paragraph(text)
    assert "きっと" not in refined


def test_no_false_positive_partial_matches(refiner):
    """部分一致の誤爆（なくなる、重ねる等）が発生しないこと。"""
    text = "希望がなくなることはない。本を重ねる。"
    refined, _, _ = refiner.refine_paragraph(text)
    assert "なくなる" in refined
    assert "重ねる" in refined
