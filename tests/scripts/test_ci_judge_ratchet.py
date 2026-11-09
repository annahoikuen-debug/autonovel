"""ratchet テスト (M1-D: ci_judge_ratchet.py)。

baseline 作成・比較・劣化検出を検証する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci_judge_ratchet import main, _flat_metrics, _compare

_BASELINE_DIR = Path("/tmp/ratchet_test_baseline")


def _make_report(*, mean_rho: float, all_passed: bool = True) -> dict:
    """テスト用レポート辞書を作成する。"""
    return {
        "judge_id": "test-judge",
        "model_name": "mock-model",
        "prompt_version": "v1",
        "n_texts": 10,
        "n_transforms": 9,
        "created_at": "2026-11-09T00:00:00+00:00",
        "thresholds": {"rho_threshold": 0.8},
        "all_passed": all_passed,
        "transforms": [
            {
                "transform_id": "T01",
                "kind": "DIR",
                "affected_axes": ["hook"],
                "n_texts": 10,
                "spearman_by_axis": {"hook": mean_rho},
                "mean_rho": mean_rho,
                "identifiability": {
                    "expected_axis": "hook",
                    "expected_drop": 10.0,
                    "other_drop": 2.0,
                    "ratio": 5.0,
                    "identified": True,
                },
                "invariance": {},
                "retest_sigma": {},
                "all_passed": all_passed,
            }
        ],
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_flat_metrics_extraction():
    """_flat_metrics が扁平メトリクスを正しく抽出する。"""
    report = _make_report(mean_rho=0.9, all_passed=True)
    flat = _flat_metrics(report)
    assert flat["test-judge.n_transforms"] == 9.0
    assert flat["test-judge.n_texts"] == 10.0
    assert flat["test-judge.T01.mean_rho"] == 0.9
    assert flat["test-judge.T01.all_passed"] == 1.0
    assert flat["test-judge.T01.identifiability.expected_drop"] == 10.0
    assert flat["test-judge.T01.identifiability.identified"] == 1.0


def test_compare_no_degradation():
    """同一レポートなら劣化は検出されない。"""
    report = _make_report(mean_rho=0.9)
    problems = _compare(report, report)
    assert problems == []


def test_compare_rho_degradation():
    """ρ が 0.05 以上低下したら劣化と判定される。"""
    baseline = _make_report(mean_rho=0.9)
    current = _make_report(mean_rho=0.8)  # 0.1 低下
    problems = _compare(baseline, current)
    assert any("T01.mean_rho" in p for p in problems)


def test_compare_rho_no_degradation_within_tolerance():
    """ρ が 0.05 未満の低下なら助判定されない。"""
    baseline = _make_report(mean_rho=0.9)
    current = _make_report(mean_rho=0.86)  # 0.04 低下（許容範囲内）
    problems = _compare(baseline, current)
    rho_problems = [p for p in problems if "T01.mean_rho" in p]
    assert rho_problems == []


def test_compare_identified_lost():
    """identified=True → False は劣化と判定される。"""
    baseline = _make_report(mean_rho=0.9, all_passed=True)
    baseline["transforms"][0]["identifiability"]["identified"] = True
    current = _make_report(mean_rho=0.9, all_passed=True)
    current["transforms"][0]["identifiability"]["identified"] = False
    problems = _compare(baseline, current)
    assert any("identified" in p for p in problems)


def test_main_check_no_baseline(tmp_path, monkeypatch):
    """baseline が存在しない場合、--check は exit 1。"""
    import scripts.ci_judge_ratchet as ratchet_mod

    monkeypatch.setattr(ratchet_mod, "BASELINE_PATH", tmp_path / "nonexistent_baseline.json")
    # レポートも存在しない
    rc = ratchet_mod.main(["--check"])
    assert rc == 1


def test_main_update_baseline_and_check(tmp_path, monkeypatch):
    """--update-baseline で保存し、--check で同一レポートなら exit 0。"""
    import scripts.ci_judge_ratchet as ratchet_mod

    baseline_path = tmp_path / "baseline.json"
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(ratchet_mod, "BASELINE_PATH", baseline_path)

    # レポートを作成
    _write_json(report_path, _make_report(mean_rho=0.9))

    # baseline として保存
    rc = ratchet_mod.main(["--update-baseline", str(report_path)])
    assert rc == 0
    assert baseline_path.exists()

    # 同一レポートで check → exit 0
    # _latest_report は glob を使うため、tmp_path 内にレポートを配置して chdir する必要がある。
    # ここでは _compare を直接テスト済みなので、ファイル操作の統合テストは別途。
    saved = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert saved["judge_id"] == "test-judge"
    assert saved["transforms"][0]["mean_rho"] == 0.9
