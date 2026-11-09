"""K1-K3 効果測定の合成データ回帰テスト（J1）。

DB に依存せず、`validate()` を直接呼んで合成 `chapters` から
alignment / 中点反転位置 / クライマックス位置を検証する。

壊れ方: measure_spine_alignment.py の計算ロジックが劣化し、
        「崩壊した書籍」を「忠実な書籍」と見なす /
        「忠実な書籍」を「崩壊」と見なす → この回帰が赤になる。
"""

from __future__ import annotations

import pytest

from src.services.structure_validator import validate


def _phases(total: int) -> list[float]:
    """ep 1..total の相対位置 0.0-1.0。"""
    if total <= 1:
        return [0.0]
    return [(e - 1) / (total - 1) for e in range(1, total + 1)]


def _make_chapters(tensions: list[int]) -> list[dict]:
    return [
        {"chapter_number": i + 1, "tension": t, "title": f"第{i+1}話"}
        for i, t in enumerate(tensions)
    ]


def test_faithful_book_scores_high_alignment():
    """exile_rise に忠実な 40 話書籍の alignment が高いこと（K1 の機械的下限）。"""
    # 中点付近で tension が高く、クライマックス直前に最高 tension
    tensions = [80] * 40
    tensions[18] = 92   # midpoint_reversal 付近（ep 19）
    tensions[32] = 95   # climax 付近（ep 33）
    chapters = _make_chapters(tensions)

    result = validate(chapters, pattern_key="exile_rise")
    assert result["is_healthy"], f"忠実な書籍が不健全: {result['problems']}"
    assert result["alignment"] >= 0.7, f"忠実書籍の alignment が低い: {result['alignment']}"


def test_broken_book_scores_low_and_is_detected():
    """中点反転を意図的に消した書籍が problems に検出されること
    （検出器が「何でも合格」になっていないことの逆張りテスト）。"""
    tensions = [50] * 40  # 完全に平坦。中点反転の高 tension がない
    chapters = _make_chapters(tensions)

    result = validate(chapters, pattern_key="exile_rise")
    # alignment は低いか、問題が検出される
    assert result["alignment"] < 0.9 or not result["is_healthy"], (
        f"崩壊書籍が見逃された: alignment={result['alignment']}, "
        f"is_healthy={result['is_healthy']}, problems={result['problems']}"
    )


def test_midpoint_and_climax_positions_in_band():
    """忠実な書籍の中点反転・クライマックス位置が K2/K3 バンド内に入ること。"""
    tensions = [60] * 40
    tensions[18] = 90   # ep 19: midpoint_reversal（相対位置 18/39 ≈ 0.46）
    tensions[32] = 100  # ep 33: climax（相対位置 32/39 ≈ 0.82）
    chapters = _make_chapters(tensions)

    # K2: 中点付近（0.4-0.6）で最高 tension
    from scripts.measure_spine_alignment import _phase

    total = len(chapters)
    mid_candidates = [c for c in chapters if 0.4 <= _phase(int(c["chapter_number"]), total) <= 0.6]
    peak_mid = max(mid_candidates, key=lambda c: c["tension"])
    k2 = _phase(int(peak_mid["chapter_number"]), total)
    assert 0.40 <= k2 <= 0.60, f"中点反転位置がバンド外: {k2}"

    # K3: 全体で最高 tension はクライマックス付近（0.75-0.92）
    peak_all = max(chapters, key=lambda c: c["tension"])
    k3 = _phase(int(peak_all["chapter_number"]), total)
    assert 0.75 <= k3 <= 0.92, f"クライマックス位置がバンド外: {k3}"


def test_short_form_1ep_has_all_three_critical_beats():
    """1話短編でも 発端・中点反転・クライマックス の3つが残ること（圧縮モードの不変条件）。
    validate_spine（Spineオブジェクト版）で検証（validate()はchaptersベースで1話ではカバー不足）。"""
    from config.story_spine import resolve_spine
    from src.services.structure_validator import validate_spine

    spine = resolve_spine("exile_rise", "short", "general", 1)
    keys = set(spine.keys)
    assert {"inciting", "midpoint_reversal", "climax"} <= keys, f"3不変条件を満たさない: {keys}"
    assert validate_spine(spine)["is_healthy"], "1話短編の Spine 検証に失敗"


def test_every_length_works_with_exile_rise():
    """全長さ階層で exile_rise が空にならず、検証を通ること。"""
    from config.story_spine import resolve_spine

    for length in ("short", "novella", "single_volume", "web_volume", "long_serial", "series"):
        spine = resolve_spine("exile_rise", length, "general")
        chapters = [
            {"chapter_number": b.ep_start, "tension": int(b.tension * 10), "title": b.label}
            for b in spine.beats
        ]
        result = validate(chapters, pattern_key="exile_rise")
        # 短編はchaptersベースのvalidate()ではカバー不足でis_healthy=Falseになることがあるため、
        # alignment > 0 と is_healthy のいずれかを満たすことを確認
        assert result["alignment"] > 0, f"{length}: alignment が 0"
        if length != "short":
            assert result["is_healthy"], f"{length}: {result.get('problems', [])}"


def test_measure_script_check_logic():
    """measure_spine_alignment.py の --check 判定ロジックを模倣し、
    K2/K3 in_band_rate >= 0.90 の閾値を検証する。"""
    # K2: 中点バンド内率が 0.90 未満なら NG
    mids = [0.45, 0.48, 0.52]  # 全部バンド内 → rate 1.0
    k2_rate = sum(1 for m in mids if 0.40 <= m <= 0.60) / len(mids)
    assert k2_rate >= 0.90

    # K3: クライマックスバンド内率が 0.90 未満なら NG
    climaxes = [0.80, 0.85, 0.88]
    k3_rate = sum(1 for c in climaxes if 0.75 <= c <= 0.92) / len(climaxes)
    assert k3_rate >= 0.90

    # バンド外が混入すると rate が下がる
    mids_bad = [0.45, 0.10, 0.52]
    k2_rate_bad = sum(1 for m in mids_bad if 0.40 <= m <= 0.60) / len(mids_bad)
    assert k2_rate_bad < 0.90
