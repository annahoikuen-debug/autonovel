"""最大ファイル（1389 行）・無カバレッジの ``src/agents/audit_agent.py`` に最低限の smoke を置く。

完全カバレッジは本計画の範囲外だが、
- import できない
- 公開定数が消える/改名される
- ``evaluate_gate`` のゲート判定ロジックが壊れる

という级别的回帰は検出できるようにする。
"""
from __future__ import annotations

import ast
import inspect

import src.agents.audit_agent as m


def test_audit_agent_module_imports():
    assert m.AuditAgent is not None
    assert inspect.isclass(m.AuditAgent)


def test_public_gate_constants_keep_their_contract():
    """環境変数で上書きされる前の既定値が、仕様どおりのまま存在すること。"""
    assert m.DEFAULT_AUDIT_GATE_THRESHOLD == 70.0
    assert m.DEFAULT_AUDIT_ADVISORY_THRESHOLD == 80.0
    assert m.AUDIT_GATE_PASS_SCORE == 100.0
    assert m.AUDIT_GATE_ADVISORY_SEVERITIES == ("medium", "low")


def _outcome(audit_id: str, score: float, *, passed: bool, severity: str, weight: float = 1.0):
    return {
        "audit_id": audit_id,
        "score": score,
        "weight": weight,
        "passed": passed,
        "blocking": True,
        "effective_severity": severity,
    }


def test_evaluate_gate_passes_when_every_audit_passes(monkeypatch):
    monkeypatch.setattr(m, "is_score_gate_enabled", lambda: True)
    res = m.evaluate_gate([_outcome("a", 95.0, passed=True, severity="none")])
    assert res["requires_regeneration"] is False, res
    assert res["failed_count"] == 0, res
    assert res["aggregate_score"] == 95.0, res
    assert res["scored_audit_ids"] == ["a"], res


def test_evaluate_gate_requires_regeneration_on_critical_failure(monkeypatch):
    """閾値以上の点数でも critical 失敗があれば再執筆を要求すること。"""
    monkeypatch.setattr(m, "is_score_gate_enabled", lambda: True)
    monkeypatch.setattr(m, "is_advisory_strict_guard_enabled", lambda: False)
    res = m.evaluate_gate(
        [
            _outcome("a", 100.0, passed=True, severity="none"),
            _outcome("b", 40.0, passed=False, severity="critical"),
        ]
    )
    assert res["critical_failure"] is True, res
    assert res["requires_regeneration"] is True, res
    assert res["advisory"] is False, res


def test_evaluate_gate_advisory_band_relaxes_medium_only_failures(monkeypatch):
    """score_aggregation + medium のみ失敗 + advisory 以上なら警告通過になること。

    advisory 帯の発火条件は
    ``advisory_threshold < threshold`` かつ ``aggregate >= advisory_threshold``。
    threshold を既定 70 より上げた場合は strict guard が優先されるため、
    ここでは「手動の厳格化をしていない」ケース（strict guard を切ってある）を検証する。
    """
    monkeypatch.setattr(m, "is_score_gate_enabled", lambda: True)
    monkeypatch.setattr(m, "is_advisory_strict_guard_enabled", lambda: False)
    monkeypatch.setattr(m, "get_gate_threshold", lambda: 90.0)
    monkeypatch.setattr(m, "get_advisory_threshold", lambda: 80.0)
    res = m.evaluate_gate([_outcome("a", 85.0, passed=False, severity="medium")])
    assert res["advisory"] is True, res
    assert res["requires_regeneration"] is False, res
    assert "警告通過" in res["advisory_reason"], res


def test_evaluate_gate_strict_guard_prevents_relaxation(monkeypatch):
    """threshold を手動で上げた場合は advisory 緩和が発火しないこと（W4 Step 11 の実バグ）。

    ``strict_guard`` は「gate 閾値 > 既定 70 かつ advisory 閾値は既定 80 のまま」で
    成立する。成立すると advisory 帯は緩和を拒否し、再執筆を要求し続ける。
    """
    monkeypatch.setattr(m, "is_score_gate_enabled", lambda: True)
    monkeypatch.setattr(m, "is_advisory_strict_guard_enabled", lambda: True)
    monkeypatch.setattr(m, "get_gate_threshold", lambda: 99.0)
    monkeypatch.setattr(m, "get_advisory_threshold", lambda: m.DEFAULT_AUDIT_ADVISORY_THRESHOLD)
    res = m.evaluate_gate([_outcome("a", 85.0, passed=False, severity="medium")])
    assert res["advisory"] is False, res
    assert res["requires_regeneration"] is True, res


def test_evaluate_gate_all_or_nothing_mode_ignores_scores(monkeypatch):
    monkeypatch.setattr(m, "is_score_gate_enabled", lambda: False)
    res = m.evaluate_gate(
        [
            _outcome("a", 100.0, passed=True, severity="none"),
            _outcome("b", 10.0, passed=False, severity="medium"),
        ]
    )
    assert res["mode"] == "all_or_nothing", res
    assert res["requires_regeneration"] is True, res


def test_evaluate_gate_ignores_non_blocking_outcomes_when_blocking_exist(monkeypatch):
    """blocking が 1 つでもあれば非 blocking はスコア計算から除外されること。"""
    monkeypatch.setattr(m, "is_score_gate_enabled", lambda: True)
    res = m.evaluate_gate(
        [
            _outcome("blocking", 72.0, passed=True, severity="none"),
            {**_outcome("advisory_only", 0.0, passed=False, severity="low"), "blocking": False},
        ]
    )
    assert res["scored_audit_ids"] == ["blocking"], res
    assert res["aggregate_score"] == 72.0, res


def test_audit_agent_has_no_network_call_at_import():
    """import 時にネットワーク通信が無いこと（ast でモジュールトップレベルを検査）。"""
    tree = ast.parse(inspect.getsource(m))
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            rendered = ast.unparse(node.value.func)
            assert "get" not in rendered and "post" not in rendered, (
                f"import 時に HTTP 呼び出ししている: {rendered}"
            )