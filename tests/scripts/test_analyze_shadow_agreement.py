"""M6: analyze_shadow_agreement テスト。

- analyze_shadow_agreement: 一致率計算、閾値判定、不一致詳細
- main: テスト用 JSON ファイルからの入力
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analyze_shadow_agreement import analyze_shadow_agreement


def _make_row(book_id: int, ep_num: int, is_passed: bool, score: float) -> dict:
    return {
        "book_id": book_id,
        "ep_num": ep_num,
        "is_passed": is_passed,
        "final_score": score,
        "created_at": "2026-11-09T00:00:00+00:00",
    }


# ---- 正常なペアリング ----


def test_analyze_full_agreement():
    """全件一致 → agreement_rate=1.0, recommend_switch=True."""
    single = [_make_row(1, 1, True, 80.0), _make_row(1, 2, False, 60.0)]
    shadow = [_make_row(1, 1, True, 78.0), _make_row(1, 2, False, 55.0)]

    result = analyze_shadow_agreement(single, shadow, agreement_threshold=0.8)

    assert result["total_pairs"] == 2
    assert result["agree_count"] == 2
    assert result["disagree_count"] == 0
    assert result["agreement_rate"] == 1.0
    assert result["recommend_switch"] is True
    assert result["recommended_mode"] == "percentile"


def test_analyze_no_agreement():
    """全件不一致 → agreement_rate=0.0, recommend_switch=False."""
    single = [_make_row(1, 1, True, 80.0)]
    shadow = [_make_row(1, 1, False, 60.0)]

    result = analyze_shadow_agreement(single, shadow, agreement_threshold=0.8)

    assert result["total_pairs"] == 1
    assert result["agree_count"] == 0
    assert result["disagree_count"] == 1
    assert result["agreement_rate"] == 0.0
    assert result["recommend_switch"] is False
    assert result["recommended_mode"] == "absolute"


# ---- 閾値境界 ----


def test_analyze_threshold_exact():
    """閾値ちょうど 0.8 → recommend_switch=True。"""
    single = [_make_row(i, i, i % 2 == 0, float(70 + i)) for i in range(10)]
    # 最初の8件は一致、最後の2件は is_passed を反転させて不一致にする
    shadow = [_make_row(i, i, i % 2 == 0, float(70 + i)) for i in range(8)] + [
        _make_row(8, 8, False, 70.0),  # single: True, shadow: False → 不一致
        _make_row(9, 9, True, 79.0),   # single: False, shadow: True → 不一致
    ]
    # 8件一致 / 10件 = 0.8

    result = analyze_shadow_agreement(single, shadow, agreement_threshold=0.8)

    assert result["agreement_rate"] == 0.8
    assert result["recommend_switch"] is True


def test_analyze_threshold_below():
    """閾値未満 (0.79) → recommend_switch=False。"""
    single = [_make_row(i, i, True, 80.0) for i in range(100)]
    shadow = [_make_row(i, i, True, 80.0) for i in range(79)] + [
        _make_row(i, i, False, 60.0) for i in range(79, 100)
    ]

    result = analyze_shadow_agreement(single, shadow, agreement_threshold=0.8)

    assert result["agreement_rate"] == 0.79
    assert result["recommend_switch"] is False


# ---- 空・不一致キー ----


def test_analyze_empty():
    """空リスト → total_pairs=0, recommend_switch=False。"""
    result = analyze_shadow_agreement([], [], agreement_threshold=0.8)

    assert result["total_pairs"] == 0
    assert result["agreement_rate"] == 0.0
    assert result["recommend_switch"] is False


def test_analyze_unmatched_keys():
    """key が一致しないレコードは無視される。"""
    single = [_make_row(1, 1, True, 80.0), _make_row(2, 2, False, 60.0)]
    shadow = [_make_row(1, 1, True, 78.0)]  # (2,2) は shadow にない

    result = analyze_shadow_agreement(single, shadow, agreement_threshold=0.8)

    assert result["total_pairs"] == 1
    assert result["agree_count"] == 1


# ---- 不一致詳細 ----


def test_analyze_disagree_details():
    """不一致詳細が含まれる。"""
    single = [_make_row(1, 1, True, 80.0)]
    shadow = [_make_row(1, 1, False, 60.0)]

    result = analyze_shadow_agreement(single, shadow, agreement_threshold=0.8)

    assert len(result["disagree_details"]) == 1
    detail = result["disagree_details"][0]
    assert detail["book_id"] == 1
    assert detail["ep_num"] == 1
    assert detail["single_is_passed"] is True
    assert detail["shadow_is_passed"] is False
    assert detail["single_score"] == 80.0
    assert detail["shadow_score"] == 60.0


# ---- カスタム閾値 ----


def test_analyze_custom_threshold():
    """カスタム閾値が反映される。"""
    single = [_make_row(1, 1, True, 80.0), _make_row(1, 2, True, 70.0)]
    shadow = [_make_row(1, 1, True, 78.0), _make_row(1, 2, False, 60.0)]

    # 50% 一致。閾値 0.5 なら True、0.6 なら False
    result_05 = analyze_shadow_agreement(single, shadow, agreement_threshold=0.5)
    assert result_05["recommend_switch"] is True

    result_06 = analyze_shadow_agreement(single, shadow, agreement_threshold=0.6)
    assert result_06["recommend_switch"] is False


# ---- main (JSON ファイル入力) ----


def test_main_with_json_files(tmp_path):
    """--single-rows/--shadow-rows で JSON ファイル入力。"""
    from scripts.analyze_shadow_agreement import main

    single_path = tmp_path / "single.json"
    shadow_path = tmp_path / "shadow.json"
    single_path.write_text(
        json.dumps([_make_row(1, 1, True, 80.0)]), encoding="utf-8"
    )
    shadow_path.write_text(
        json.dumps([_make_row(1, 1, True, 78.0)]), encoding="utf-8"
    )

    rc = main(
        [
            "--single-rows",
            str(single_path),
            "--shadow-rows",
            str(shadow_path),
        ]
    )
    assert rc == 0  # 一致 → recommend_switch=True でも --recommend なしなら 0

    # --recommend 付きで yaml 更新は行わない (ファイルパスが一時的なので)
    rc = main(
        [
            "--single-rows",
            str(single_path),
            "--shadow-rows",
            str(shadow_path),
            "--recommend",
        ]
    )
    assert rc == 0
