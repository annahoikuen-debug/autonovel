"""RepairPlan 決定ロジックの回帰テスト。"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.audit.static_rules import Issue, StaticRuleAuditor
from src.audit.repair_planner import plan_repair

TEXT = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"


def test_critical_static_issue_defers_to_human():
    issues = [Issue("paragraph_count_insufficient", "x", None, None, "critical")]
    assert plan_repair(TEXT, [], issues).level == "none"


def test_only_line_punct_issues_use_rule_level():
    issues = [Issue("line_start_forbidden_punct", "x", (0, 1), None, "minor")]
    assert plan_repair(TEXT, [], issues).level == "rule"


def test_major_outcome_escalates_to_scene():
    out = [{"audit_id": "causal_integrity", "severity": "critical", "error": None}]
    assert plan_repair(TEXT, out, []).level == "scene"


def test_medium_outcome_uses_span_level_with_targets():
    out = [{"audit_id": "deai", "severity": "medium", "error": None,
            "feedback": "古代の魔導書"}]
    plan = plan_repair(TEXT, out, [])
    assert plan.level == "span"
    assert plan.targets and TEXT.count("\n\n") >= 0


def test_span_level_without_targets_degrades_to_none():
    plan = plan_repair("   ", [{"audit_id": "deai", "severity": "medium", "error": None}], [])
    assert plan.level == "none"


def test_no_failures_returns_none():
    assert plan_repair(TEXT, [], []).level == "none"
