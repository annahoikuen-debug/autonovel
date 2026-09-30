"""短編圧縮モードの不変条件。本計画で最も重要なテスト群。"""

import pytest

from config.story_spine import PATTERNS
from src.services.spine_resolver import resolve_spine

PATTERN_KEYS = sorted(PATTERNS)


@pytest.mark.parametrize("pattern", PATTERN_KEYS)
def test_single_episode_preserves_three_critical_beats(pattern):
    """1話短編でも 発端・中点反転・クライマックス の3つは必ず残る。"""
    spine = resolve_spine(pattern, "short", "general", total_eps=1)
    keys = spine.keys
    assert keys[0] in ("inciting", "humiliation", "cold_open", "revelation"), (
        f"{pattern}: 最初がつかみになっていない: {keys}"
    )
    assert "midpoint_reversal" in keys, f"{pattern}: 中点反転が消えている: {keys}"
    assert "climax" in keys, f"{pattern}: クライマックスが消えている: {keys}"


@pytest.mark.parametrize("pattern", PATTERN_KEYS)
def test_single_episode_ends_with_climax(pattern):
    """短編の最後がクライマックスでないと結末が無い。"""
    spine = resolve_spine(pattern, "short", "general", total_eps=1)
    assert spine.keys[-1] == "climax", f"{pattern}: 最後が {spine.keys[-1]!r} になっている"


@pytest.mark.parametrize("eps", [1, 2, 3, 4, 5, 8, 12])
def test_beat_count_never_shrinks_as_length_grows(eps):
    """話数を増やすと beat 数が減らないこと。"""
    prev = 0
    for e in range(1, eps + 1):
        n = len(resolve_spine("exile_rise", "short", "general", total_eps=e).beats)
        assert n >= prev, f"eps={e} で beat が {prev}→{n} に減った"
        prev = n


@pytest.mark.parametrize("eps", [1, 2, 3, 5, 10])
def test_critical_beats_survive_at_every_short_length(eps):
    for pattern in PATTERN_KEYS:
        keys = resolve_spine(pattern, "short", "general", total_eps=eps).keys
        assert "midpoint_reversal" in keys, f"{pattern}@{eps}: 中点反転が消えた {keys}"
        assert "climax" in keys, f"{pattern}@{eps}: クライマックスが消えた {keys}"


def test_web_market_keeps_volume_hook():
    """Web 連載では話末の引きが消えない。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", total_eps=40)
    assert spine.keys[-1] == "volume_hook", spine.keys[-3:]


def test_general_market_drops_volume_hook():
    """一般文芸では「次への引き」を強制しない。"""
    spine = resolve_spine("exile_rise", "single_volume", "general", total_eps=18)
    assert "volume_hook" not in spine.keys


def test_single_episode_keeps_all_duties_merged():
    """圧縮された beat の duty は統合されている（元の文が消えていない）。"""
    spine = resolve_spine("exile_rise", "short", "general", total_eps=1)
    inciting = spine.at(1)
    assert "、" in inciting.duty, f"duty が統合されていない: {inciting.duty!r}"
    assert len(inciting.duty) <= 60, f"duty が長すぎる: {len(inciting.duty)}字"


def test_short_form_every_episode_has_a_beat():
    for pattern in PATTERN_KEYS:
        for eps in (1, 2, 3):
            spine = resolve_spine(pattern, "short", "general", total_eps=eps)
            for ep in range(1, eps + 1):
                assert spine.at(ep) is not None, f"{pattern}@{eps}: 第{ep}話に beat が無い"
