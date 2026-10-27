"""TargetedDiagnostic が実際に段落を1件以上返すことの回帰テスト。"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.audit.targeted_diagnostic import TargetedDiagnostic


def test_returns_empty_without_text_backward_compatible():
    assert TargetedDiagnostic().identify_weak_paragraphs({"feedback": "x"}) == []


def test_matches_paragraph_containing_feedback_quote():
    text = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"
    targets = TargetedDiagnostic().identify_weak_paragraphs(
        {"feedback": "古代の魔導書"}, text=text
    )
    assert len(targets) == 1
    assert targets[0].index == 1
    assert "魔導書" in targets[0].original_text
    assert targets[0].directive == "古代の魔導書"


def test_falls_back_to_last_paragraph_when_no_quote_match():
    text = "あ。\n\nい。\n\nう。"
    targets = TargetedDiagnostic().identify_weak_paragraphs({"feedback": "存在しない語"}, text=text)
    assert len(targets) == 1 and targets[0].index == 2


def test_caps_at_max_targets():
    text = "\n\n".join(f"魔導書段落{i}" for i in range(10))
    targets = TargetedDiagnostic(max_targets=3).identify_weak_paragraphs(
        {"feedback": "魔導書"}, text=text
    )
    assert len(targets) == 3
