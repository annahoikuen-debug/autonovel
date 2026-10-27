"""**バリデータの期待位置が patterns.yaml の span から来ること**の構造テスト。

レビューで「400/414 が乖離」「乱数でも 27% が健全」と判定された。
本テストは SSOT を固定し、以後の乖離を再発させない。
"""
from __future__ import annotations

import random

import pytest

from config.story_spine import PATTERNS, resolve_spine
from src.services.structure_validator import (
    check_required_beats,
    load_pattern_beats,
    validate,
)


def test_expected_phase_comes_from_pattern_yaml_not_vocabulary():
    """**SSOT は patterns.yaml**。BEAT_VOCABULARY の span を使ってはならない。"""
    offenders = []
    for pk in sorted(PATTERNS):
        struct = load_pattern_beats(pk)
        yaml_spans = {b["key"]: b["span"] for b in PATTERNS[pk]["beats"]}
        for rb in struct["required_beats"]:
            expected = round(sum(yaml_spans[rb["key"]]) / 2, 3)
            if rb["phase"] != expected:
                offenders.append(f"{pk}.{rb['key']}: {rb['phase']} != {expected}")
    assert not offenders, "phase が語彙 span から算出されている:\n" + "\n".join(offenders[:20])


def test_pattern_beats_declare_a_tight_tolerance():
    """パターンは位置が確定しているので、寛容幅 0.35 は破綻を隠す。"""
    struct = load_pattern_beats("exile_rise")
    assert struct["beat_tol"] == 0.10, struct.get("beat_tol")


@pytest.mark.parametrize("pk", ["exile_rise", "detective_mystery", "death_loop", "gourmet_conqueror"])
@pytest.mark.parametrize("eps", [20, 40, 60])
def test_resolver_output_passes_its_own_validator(pk: str, eps: int):
    """**resolver の出力が、自前の validator で「充足」と判定されること**。

    これが R4 の主力テスト。修正前は `missing_beats` が空にならず **赤になる**。
    """
    spine = resolve_spine(pk, "web_volume", "web", eps)
    chapters = [
        {"chapter_number": b.ep_start, "tension": int(b.tension * 100)}
        for b in spine.beats
    ]
    r = validate(chapters, pattern_key=pk)
    assert r["missing_beats"] == [], (
        f"{pk}@{eps}: resolver 出力なのに必須ビートが {len(r['missing_beats'])} 個欠落 "
        f"{[b['key'] for b in r['missing_beats'][:5]]}"
    )
    assert r["alignment"] == 1.0, f"{pk}@{eps}: alignment={r['alignment']}"


def test_random_chapters_are_not_reported_healthy():
    """**乱数データでも構造健全と判定されないこと**（= 検証器が機能している証拠）。

    修正前は 50 ケース中 27% が `is_healthy` になっていた。
    """
    rnd = random.Random(20260930)
    healthy = 0
    for _ in range(50):
        chapters = [
            {"chapter_number": i, "tension": rnd.randint(0, 10)} for i in range(1, 21)
        ]
        if validate(chapters, pattern_key="exile_rise")["is_healthy"]:
            healthy += 1
    assert healthy <= 3, (
        f"乱数 tension でも {healthy}/50 が健全と判定された。"
        "検証器が構造を一切見ていない（beat_tol が広すぎる疑い）"
    )


def test_misplaced_beats_are_actually_detected():
    """**本当にズレた構成は「不足」として検出されること**（偽陰性 0 の確認）。"""
    # 全てを前半に固める = 全必須ビートが終盤に来るはず
    chapters = [
        {"chapter_number": i, "tension": 1} for i in range(1, 6)
    ] + [
        {"chapter_number": 20 + i, "tension": 9} for i in range(5)
    ]
    r = validate(chapters, pattern_key="exile_rise")
    assert r["missing_beats"], "全部を話数 1-5 に固めたのに『不足なし』は検出漏れ"


def test_resolve_and_unknown_pattern_keys_are_both_reported():
    """入力値と実評価値を両方出すこと（表示と実態の不一致の解消）。"""
    r = validate([{"chapter_number": 1, "tension": 1}], pattern_key="nope")
    assert r["pattern_key"] == "nope"
    assert r["resolved_pattern_key"] == "exile_rise", r


def test_legacy_structures_keep_their_wide_tolerance():
    """後方互換：従来 3 構造の挙動を変えない。"""
    from src.services.structure_validator import STRUCTURE_DEFINITIONS

    assigned = [{"_phase": 0.1, "tension": 5}, {"_phase": 0.5, "tension": 9},
                {"_phase": 0.9, "tension": 3}]
    for name, struct in STRUCTURE_DEFINITIONS.items():
        out = check_required_beats(assigned, struct)
        assert isinstance(out, list) and out, name
        assert all(isinstance(b, dict) and "present" in b for b in out), name
