"""pattern 対応の構造バリデータ。"""

from src.services.structure_validator import (
    assign_phases,
    check_spine_invariants,
    load_pattern_beats,
    validate,
    validate_spine,
)
from src.services.spine_resolver import resolve_spine


def test_legacy_structures_still_work():
    """既存 API が壊れていないこと（後方互換の回帰防止）。"""
    r = validate([{"chapter_number": 1, "tension": 1}], structure_name="kishotenketsu")
    assert r["structure_key"] == "kishotenketsu"
    assert r["pattern_key"] is None
    assert "is_healthy" in r


def test_pattern_key_uses_spine_beats():
    chapters = [{"chapter_number": i, "tension": int(10 * i)} for i in range(1, 21)]
    r = validate(chapters, structure_name="three_act", pattern_key="exile_rise")
    assert r["pattern_key"] == "exile_rise"
    assert r["required_beat_count"] == 11
    assert isinstance(r["missing_beats"], list)
    assert 0.0 <= r["alignment"] <= 1.0


def test_unknown_pattern_falls_back():
    r = validate([{"chapter_number": 1, "tension": 1}], pattern_key="nope")
    assert r["pattern_key"] == "nope"
    assert r["resolved_pattern_key"] == "exile_rise"
    assert r["required_beat_count"] > 0, "未知パターンでも既定パターンで評価する"


def test_every_pattern_loads_beats():
    """38パターンすべてで必須ビートが構築できること。"""
    from config.story_spine import PATTERNS

    for key in PATTERNS:
        beats = load_pattern_beats(key)["required_beats"]
        assert beats, f"{key} で必須ビートが構築できなかった"
        assert all(0.0 <= b["phase"] <= 1.0 for b in beats), f"{key}: phase が範囲外"


def test_alignment_is_one_for_a_faithful_spine():
    """展開済みの Spine をそのまま渡すと充足度が立つこと。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    chapters = [{"chapter_number": ep, "tension": int(spine.at(ep).tension * 10)} for ep in range(1, 41)]
    r = validate(chapters, pattern_key="exile_rise")
    assert r["alignment"] == 1.0
    assert r["total_chapters"] == 40


def test_validate_spine_passes_for_healthy_spine():
    """生成前検証（Spine 自身）が正常な構造で通ること。"""
    result = validate_spine(resolve_spine("exile_rise", "web_volume", "web", 40))
    assert result["is_healthy"], result["problems"]
    assert result["beat_count"] == 11
    assert result["total_eps"] == 40


def test_validate_spine_passes_for_single_episode():
    """1話短編でも検証を通ること（短編が常に『不健康』になるのを防ぐ）。"""
    result = validate_spine(resolve_spine("exile_rise", "short", "general", 1))
    assert result["is_healthy"], result["problems"]


def test_validate_spine_detects_empty_spine():
    class _Empty:
        beats = []
        total_eps = 5
        pattern = length = market = "x"

    result = validate_spine(_Empty())
    assert not result["is_healthy"]


def test_assign_phases_single_chapter_does_not_divide_by_zero():
    """1話構成で ZeroDivisionError しないこと（短編対応の回帰）。"""
    out = assign_phases([{"chapter_number": 1, "title": "短編"}])
    assert out[0]["_phase"] == 0.0


def test_check_spine_invariants_reports_missing_beat():
    """beats が空の Spine は coverage 違反として報告される。"""

    class _Partial:
        beats = []
        total_eps = 3
        pattern = length = market = "x"

    problems = check_spine_invariants(_Partial(), 3)
    assert problems
