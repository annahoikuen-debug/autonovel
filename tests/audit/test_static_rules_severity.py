"""StaticRuleAuditor の Issue に severity が載ることを確認する回帰テスト。"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.audit.static_rules import StaticRuleAuditor


def test_issue_has_severity_field():
    auditor = StaticRuleAuditor()
    issues = auditor.audit("あ" * 6000)  # 文字数超過
    assert issues, "length_exceeded が出るはず"
    assert all(hasattr(i, "severity") for i in issues)
    assert next(i for i in issues if i.type == "length_exceeded").severity == "major"


def test_paragraph_count_insufficient_is_critical():
    issues = StaticRuleAuditor().audit("   ")
    assert any(
        i.type == "paragraph_count_insufficient" and i.severity == "critical" for i in issues
    )


def test_line_start_punct_is_minor():
    text = "タイトル\n\n「これは冒頭引用だ。\n普通の行。"
    issues = StaticRuleAuditor().audit(text)
    hit = [i for i in issues if i.type == "line_start_forbidden_punct"]
    assert hit and hit[0].severity == "minor"


def test_positional_3arg_construction_still_works():
    """既存の位置引数3つ生成が壊れていないこと（後方互換の爪）。"""
    from src.audit.static_rules import Issue

    i = Issue("t", "m", (0, 1))
    assert i.severity == "minor"
    assert i.suggestion is None
