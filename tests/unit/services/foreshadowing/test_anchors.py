"""ナラティブアンカーと半開区間化の回帰テスト（PLAN_W5 Step 2）。

計画書の `test_half_open_interval_is_used` は
`beat_for_episode(10) == (11,18)` と `beat_for_episode(3) == (1,3)` の
2 条件を同時に要求しており、**単一の統一則では両方を満たせない**
（(1,3) の終了話 3 が (1,3) 側か (4,10) 側かで規則が割れる）。
ここでは計画書の意図どおり「境界話は次のビート」を採用し、
整合する形でAssertions を書き直している。
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.services.foreshadowing.anchors import (  # noqa: E402
    ANCHOR_NAMES,
    BEAT_RANGE_IS_HALF_OPEN,
    PAYOFF_ANCHORS,
    anchor_episode,
    beat_for_episode,
    is_anchor_episode,
)


def test_half_open_interval_is_used():
    """(4,10) の半開区間なので第10話は (11,18) に属する。"""
    assert BEAT_RANGE_IS_HALF_OPEN is True
    assert beat_for_episode(10)["range"] == (11, 18)
    assert beat_for_episode(4)["range"] == (4, 10)
    assert beat_for_episode(1)["range"] == (1, 3)
    assert beat_for_episode(2)["range"] == (1, 3)


def test_boundary_episode_moves_to_next_beat():
    """各ビートの終了話は「次のビート」に属する（統一則）。"""
    assert beat_for_episode(3)["range"] == (4, 10)
    assert beat_for_episode(18)["range"] == (19, 25)
    assert beat_for_episode(38)["range"] == (39, 40)


def test_out_of_range_falls_back_to_last_beat():
    assert beat_for_episode(999)["range"] == (39, 40)


def test_anchor_episode_returns_range_start():
    for name in ANCHOR_NAMES:
        assert anchor_episode(name) >= 1, name


def test_anchor_episode_values_are_ordered():
    """物語進行顺着アンカーが昇順になること。"""
    order = [anchor_episode(n) for n in ANCHOR_NAMES]
    assert order == sorted(order), order
    assert anchor_episode("midpoint") == 19
    assert anchor_episode("climax") == 33
    assert anchor_episode("resolution") == 39


def test_payoff_anchor_membership():
    assert is_anchor_episode(anchor_episode("midpoint")) is True
    assert is_anchor_episode(anchor_episode("climax")) is True
    assert is_anchor_episode(2) is False


def test_payoff_anchors_tuple_is_frozen():
    assert PAYOFF_ANCHORS == ("midpoint", "climax", "resolution")


def test_unknown_anchor_does_not_raise():
    assert anchor_episode("no-such-anchor") == 39
    assert is_anchor_episode("not-an-int") is False
