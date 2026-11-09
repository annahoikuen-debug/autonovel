"""T-M1: 擾乱ラダー評価メトリクステスト。

- Spearman ρ: 完全単調・完全逆順・タイあり・n<2・分散ゼロ
- 識別性: 期待軸の低下が他軸より大きい / 等しい / 低下なし
- INV: 小さな変化で pass / 大きな変化で fail
- 再テストσ: 安定 / 不安定
"""

from __future__ import annotations

from src.audit.perturbation.metrics import (
    IdentifiabilityResult,
    InvarianceResult,
    RetestResult,
    SpearmanResult,
    check_invariance,
    check_retest_stability,
    identify_axis,
    spearman_rank,
)


# ── Spearman ρ ──


def test_spearman_perfect_positive():
    """完全単調増加なら rho=1.0。"""
    r = spearman_rank([1, 2, 3, 4], [10, 20, 30, 40])
    assert r.rho == 1.0
    assert r.n == 4


def test_spearman_perfect_negative():
    """完全単調減少なら rho=-1.0。"""
    r = spearman_rank([1, 2, 3, 4], [40, 30, 20, 10])
    assert r.rho == -1.0


def test_spearman_with_ties():
    """タイ（同順位）がある場合も平均順位で計算される。"""
    r = spearman_rank([1, 2, 2, 4], [10, 20, 20, 40])
    assert r.rho == 1.0


def test_spearman_no_correlation():
    """無相関なら rho≈0。"""
    r = spearman_rank([1, 2, 3, 4], [10, 10, 10, 10])
    assert r.rho == 0.0


def test_spearman_n_less_than_two():
    """n < 2 なら rho=0.0。"""
    r = spearman_rank([1], [10])
    assert r.rho == 0.0
    assert r.n == 1


def test_spearman_mismatched_lengths():
    """長さが異なる入力は rho=0.0。"""
    r = spearman_rank([1, 2], [10])
    assert r.rho == 0.0


# ── 識別性 ──


def test_identify_axis_detects_expected_drop():
    """期待軸の低下が他軸より大きければ identified=True。"""
    res = identify_axis(
        {"hook": 80.0, "overall": 70.0, "emotional": 75.0},
        {"hook": 60.0, "overall": 68.0, "emotional": 74.0},
        "hook",
    )
    assert res.expected_drop == 20.0
    assert res.identified is True


def test_identify_axis_equal_drop_not_identified():
    """期待軸と他軸の低下が同じなら identified=False。"""
    res = identify_axis(
        {"hook": 80.0, "overall": 70.0},
        {"hook": 60.0, "overall": 50.0},
        "hook",
    )
    assert res.expected_drop == 20.0
    assert res.other_drop == 20.0
    assert res.identified is False


def test_identify_axis_no_drop():
    """低下がない場合は identified=False。"""
    res = identify_axis(
        {"hook": 80.0, "overall": 70.0},
        {"hook": 80.0, "overall": 70.0},
        "hook",
    )
    assert res.expected_drop == 0.0
    assert res.identified is False


def test_identify_axis_unknown_axis():
    """存在しない軸を指定すると identified=False。"""
    res = identify_axis({"hook": 80.0}, {"hook": 60.0}, "nonexistent")
    assert res.identified is False


# ── INV (不変性) ──


def test_invariance_small_delta_passed():
    """全軸の |Δ| が閾値以内なら passed=True。"""
    res = check_invariance(
        {"hook": 80.0, "overall": 70.0},
        {"hook": 81.0, "overall": 69.5},
        threshold=3.0,
    )
    assert res.max_delta == 1.0
    assert res.passed is True


def test_invariance_large_delta_failed():
    """1軸でも閾値を超えれば passed=False。"""
    res = check_invariance(
        {"hook": 80.0, "overall": 70.0},
        {"hook": 84.0, "overall": 69.0},
        threshold=3.0,
    )
    assert res.max_delta == 4.0
    assert res.passed is False


# ── 再テストσ ──


def test_retest_stable_passed():
    """2回のスコアが近いなら passed=True。"""
    res = check_retest_stability(70.0, 72.0, threshold=5.0)
    assert res.sigma == 1.0
    assert res.passed is True


def test_retest_unstable_failed():
    """2回のスコアが離れていれば passed=False。"""
    res = check_retest_stability(70.0, 85.0, threshold=5.0)
    assert res.passed is False


def test_retest_identical():
    """同じスコアなら sigma=0.0。"""
    res = check_retest_stability(75.0, 75.0, threshold=5.0)
    assert res.sigma == 0.0
    assert res.passed is True
