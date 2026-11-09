"""M5-C: recompute_gate_percentile テスト。

- _percentile: 線形補間の正確性
- compute_percentile_threshold: 正常計算、空リスト、window 制限
"""

from __future__ import annotations

from scripts.recompute_gate_percentile import compute_percentile_threshold, _percentile


# ---- _percentile ----


def test_percentile_single():
    """1件ならその値。"""
    assert _percentile([50.0], 30) == 50.0


def test_percentile_empty():
    """空なら 0.0。"""
    assert _percentile([], 30) == 0.0


def test_percentile_linear_interpolation():
    """線形補間が正しく動作する。"""
    # [10, 20, 30, 40, 50] の P50 = 30
    assert _percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50) == 30.0
    # [10, 20, 30, 40, 50] の P25 = 20 (インデックス1)
    assert _percentile([10.0, 20.0, 30.0, 40.0, 50.0], 25) == 20.0
    # [10, 20, 30, 40] の P50 = 25 (インデックス1.5 の線形補間)
    assert _percentile([10.0, 20.0, 30.0, 40.0], 50) == 25.0


# ---- compute_percentile_threshold ----


def test_compute_percentile_normal():
    """正常にパーセンタイル閾値が計算される。"""
    scores = [float(i) for i in range(1, 101)]  # 1..100
    result = compute_percentile_threshold(scores, window=200, percentile=30.0)
    assert result["n"] == 100
    assert result["window"] == 200
    assert result["percentile"] == 30.0
    # P30 of 1..100: index = 99 * 0.3 = 29.7 → 間の補間
    assert 29.0 <= result["threshold"] <= 31.0
    assert result["min"] == 1.0
    assert result["max"] == 100.0


def test_compute_percentile_window_limit():
    """window で直近 N 件に制限される。"""
    scores = [float(i) for i in range(1, 101)]  # 1..100
    result = compute_percentile_threshold(scores, window=10, percentile=50.0)
    assert result["n"] == 10
    # 直近10件は 91..100、P50 = 95.5
    assert 95.0 <= result["threshold"] <= 96.0


def test_compute_percentile_empty():
    """空リスト。"""
    result = compute_percentile_threshold([], window=200, percentile=30.0)
    assert result["n"] == 0
    assert result["threshold"] is None
