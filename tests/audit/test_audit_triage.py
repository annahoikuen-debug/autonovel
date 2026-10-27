"""三段階トリアージ判定の純関数テスト。"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.audit.static_rules import Issue
from src.audit.triage import classify_static_issues, classify_audit_outcomes


def test_all_minor_when_no_issues():
    assert classify_static_issues([]) == "minor"
    assert classify_audit_outcomes([]) == "minor"


def test_static_critical_escalates_to_major():
    issues = [Issue("paragraph_count_insufficient", "x", None, None, "critical")]
    assert classify_static_issues(issues) == "major"


def test_outcome_with_error_is_major():
    out = [{"audit_id": "deai", "severity": "medium", "error": "auditor_exception:Timeout"}]
    assert classify_audit_outcomes(out) == "major"


def test_outcome_high_severity_is_medium():
    out = [{"audit_id": "fast_screen", "severity": "high", "error": None}]
    assert classify_audit_outcomes(out) == "medium"


def test_never_returns_unknown_level():
    out = [{"audit_id": "x", "severity": "unknown-value", "error": None}]
    assert classify_audit_outcomes(out) in {"minor", "medium", "major"}
