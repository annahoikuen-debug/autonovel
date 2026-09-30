"""Advisory 帯（重大ではないが合格でもない → 警告で通過）の回帰テスト。

W4 Step 9（``src/agents/audit_agent.py::evaluate_gate``）の契約テスト。

計画書からの逸脱（理由付き）:
計画書の判定順序は「requires_regeneration が False → advisory=False」だが、
``aggregate >= advisory_threshold`` は ``aggregate < threshold`` より弱い条件なので、
既定（advisory 80 > gate 70）では帯が原理的に発火せず、テストが成立しない。
そこで帯を「``advisory_threshold < threshold`` のときだけ有効（＝
``aggregate ∈ [advisory_threshold, threshold)`` を relief する）」に定義し直した。
これにより ``AUDIT_GATE_THRESHOLD`` を意図的に上げた場合の
ロールバック（手動の厳格化）が advisory に上書きされて取り消される事故も防げる。
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

import pytest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.audit_agent import (  # noqa: E402
    AUDIT_GATE_ADVISORY_SEVERITIES,
    DEFAULT_AUDIT_ADVISORY_THRESHOLD,
    evaluate_gate,
    get_advisory_threshold,
    get_gate_threshold,
)


def _outcome(
    audit_id: str,
    severity: str,
    score: float,
    passed: bool = False,
    blocking: bool = True,
) -> dict[str, Any]:
    """``AuditAgent.run_audit_phase`` が作る outcome dict の実キー構成に揃える。"""
    return {
        "audit_id": audit_id,
        "label": audit_id,
        "passed": passed,
        "feedback": "",
        "severity": severity,
        "learning_adjusted": False,
        "confidence_adjustment": 0.0,
        "effective_severity": severity,
        "error": None,
        "score": score,
        "weight": 1.0,
        "blocking": blocking,
        "detail": {},
    }


def test_advisory_threshold_default_is_80(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIT_ADVISORY_THRESHOLD", raising=False)
    assert DEFAULT_AUDIT_ADVISORY_THRESHOLD == 80.0
    assert get_advisory_threshold() == 80.0
    assert AUDIT_GATE_ADVISORY_SEVERITIES == ("medium", "low")


def test_advisory_threshold_is_env_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "42.5")
    assert get_advisory_threshold() == 42.5
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "not-a-float")
    assert get_advisory_threshold() == 80.0


def test_medium_only_failure_above_advisory_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """重大でない失敗が advisory 帯に入れば再執筆せず警告通過になること。"""
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "60")
    gate = evaluate_gate(
        [
            _outcome("deai", "medium", 100.0),
            _outcome("fast_screen", "high", 100.0, passed=True),
            _outcome("x", "medium", 50.0),
        ]
    )
    assert gate["advisory"] is True
    assert gate["requires_regeneration"] is False
    assert gate["advisory_reason"]
    assert gate["failed_count"] == 2


def test_critical_failure_never_becomes_advisory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "10")
    gate = evaluate_gate(
        [
            _outcome("causal_integrity", "critical", 100.0),
            _outcome("x", "medium", 50.0),
        ]
    )
    assert gate["advisory"] is False
    assert gate["advisory_reason"] == ""
    assert gate["requires_regeneration"] is True
    assert gate["critical_failure"] is True


def test_high_severity_failure_is_not_advisory(monkeypatch: pytest.MonkeyPatch) -> None:
    """advisory 帯は medium / low のみ。high 混在なら再執筆のまま。"""
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "10")
    gate = evaluate_gate(
        [
            _outcome("deai", "medium", 100.0),
            _outcome("fast_screen", "high", 50.0),
        ]
    )
    assert gate["advisory"] is False
    assert gate["requires_regeneration"] is True


def test_below_advisory_threshold_still_regenerates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "95")
    gate = evaluate_gate([_outcome("x", "medium", 50.0)])
    assert gate["advisory"] is False
    assert gate["requires_regeneration"] is True


def test_strict_gate_threshold_is_not_overridden_by_default_advisory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既定（advisory 80 > gate 70）では帯が空 = ``AUDIT_GATE_THRESHOLD`` の厳格化を壊さない。"""
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.delenv("AUDIT_ADVISORY_THRESHOLD", raising=False)
    outcomes = [
        _outcome("deai", "medium", 100.0),
        _outcome("fast_screen", "high", 100.0, passed=True),
        _outcome("x", "medium", 50.0),
    ]
    gate = evaluate_gate(outcomes)
    assert gate["aggregate_score"] >= 80.0
    assert gate["advisory"] is False
    assert gate["requires_regeneration"] is False  # 70.0 の既定ゲートでは元々通過

    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    strict = evaluate_gate(outcomes)
    assert strict["requires_regeneration"] is True, "手動で上げた閾値が advisory に消されている"
    assert strict["advisory"] is False


def test_rollback_via_999_disables_band(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "999")
    gate = evaluate_gate(
        [
            _outcome("deai", "medium", 100.0),
            _outcome("fast_screen", "high", 100.0, passed=True),
            _outcome("x", "medium", 50.0),
        ]
    )
    assert gate["advisory"] is False
    assert gate["requires_regeneration"] is True


def test_all_passed_is_never_advisory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "10")
    gate = evaluate_gate([_outcome("x", "medium", 100.0, passed=True)])
    assert gate["advisory"] is False
    assert gate["advisory_reason"] == ""
    assert gate["requires_regeneration"] is False


def test_legacy_keys_still_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    gate = evaluate_gate([_outcome("x", "medium", 50.0)])
    for k in (
        "mode",
        "aggregate_score",
        "threshold",
        "requires_regeneration",
        "critical_failure",
        "failed_count",
        "scored_audit_ids",
    ):
        assert k in gate, k
    assert gate["mode"] == "score_aggregation"
    assert gate["threshold"] == get_gate_threshold()


def test_all_or_nothing_mode_keeps_advisory_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """ロールバック（全滅式ゲート）でも advisory は発火しない。

    全滅式ゲートの定義は「1件でも落ちたら再執筆」なので、合格点（score 100.0）でも
    `passed=False` なら再執筆是有効である。ここで固定するのは **advisory が発火しない**
    こと（advisory は `mode == "score_aggregation"` のときだけ起作用する）。
    """
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "0")
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "10")
    gate = evaluate_gate([_outcome("x", "medium", 100.0)])
    assert gate["mode"] == "all_or_nothing"
    assert gate["advisory"] is False
    assert gate["advisory_reason"] == ""
    # 全滅式 = 1件でも落ちたら再執筆（閾値は一切見ない）
    assert gate["requires_regeneration"] is True


def test_default_threshold_with_lowered_advisory_still_relaxes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既定 threshold 70.0 + advisory 60 のとき medium のみの失敗は緩和される（契約維持）。

    W4 Step 11 の実バグB修正で「手動で上げた閾値では緩和しない」ガードを足したが、
    ``AUDIT_GATE_THRESHOLD`` を既定値のままにした場合（= 手動の厳格化なし）は
    従来の advisory 緩和が引き続きworking であることを固定する。
    """
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.delenv("AUDIT_GATE_THRESHOLD", raising=False)
    monkeypatch.delenv("ENABLE_AUDIT_ADVISORY_STRICT_GUARD", raising=False)
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "60")
    # aggregate = (100 + 30) / 2 = 65.0 → [advisory 60, threshold 70) の帯に入る
    gate = evaluate_gate(
        [
            _outcome("deai", "medium", 100.0, passed=True),
            _outcome("x", "medium", 30.0),
        ]
    )
    assert gate["threshold"] == 70.0
    assert 60.0 <= gate["aggregate_score"] < 70.0
    assert gate["advisory"] is True
    assert gate["requires_regeneration"] is False
    assert gate["advisory_reason"]
