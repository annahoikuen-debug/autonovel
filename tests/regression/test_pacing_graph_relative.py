"""**PacingGraph が話数非依存・順序が破綻しないこと**の回帰テスト。

レビューで「eps=5 で大団円がクライマックスより先」「eps=8,10 でフィナーレが到達不能」
が発見された。既存テストは 2 つの窓を 1 度も同時に踏んでいなかったため緑だった。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from config.story_spine import BEAT_VOCABULARY
from src.backend.engine_narrative import PacingGraph

EPS_LIST = (3, 5, 8, 10, 12, 16, 20, 40, 100, 300)
LABEL_RE = re.compile(r"^【(.+?)】")


def _label(ep: int, eps: int) -> str:
    instr = PacingGraph.get_instruction(ep, total_eps=eps)["instruction"]
    m = LABEL_RE.match(instr)
    return m.group(1) if m else ""


def _windows(eps: int) -> tuple[list[int], list[int]]:
    clim = [e for e in range(1, eps + 1) if _label(e, eps) == "クライマックス"]
    fin = [e for e in range(1, eps + 1) if "フィナーレ" in _label(e, eps)]
    return clim, fin


@pytest.mark.parametrize("eps", EPS_LIST)
def test_finale_never_precedes_climax(eps: int):
    """**意味の反転を検出する**。フィナーレがクライマックスより前に出てはならない。"""
    clim, fin = _windows(eps)
    if fin:
        assert min(fin) > max(clim), (
            f"eps={eps}: フィナーレ {fin} がクライマックス {clim} より前/重複"
        )


@pytest.mark.parametrize("eps", EPS_LIST)
def test_finale_appears_whenever_there_is_room(eps: int):
    """クライマックスの**後ろに話があるなら**フィナーレを出す（分岐の死を検出）。"""
    clim, fin = _windows(eps)
    assert clim, f"eps={eps}: クライマックス窓が見つからない"
    room = [e for e in range(1, eps + 1) if e > max(clim)]
    if room:
        assert fin, (
            f"eps={eps}: クライマックス（{max(clim)}話）の後に {room} 話あるのに"
            "フィナーレ分岐が発火しない（到達不能）"
        )
        assert min(fin) == room[0] or min(fin) > max(clim)


@pytest.mark.parametrize("eps", EPS_LIST)
def test_labels_depend_only_on_relative_position(eps: int):
    """(ep-1)/eps が同じなら指示が同じであること（絶対窓が残っていないことの確認）。"""
    for k in (2, 3):
        if k >= eps:
            continue
        m = 3 * (k - 1) + 1
        assert _label(k, eps) == _label(m, eps * 3), (
            f"k={k}: eps={eps} と eps={eps * 3} (m={m}) でラベルが不一致 "
            f"({_label(k, eps)!r} vs {_label(m, eps * 3)!r})"
        )


@pytest.mark.parametrize("eps", EPS_LIST)
def test_relative_position_of_climax_is_stable(eps: int):
    """クライマックスの相対位置が話数によらず終盤に留まること。"""
    clim, _ = _windows(eps)
    assert clim, eps
    assert max(clim) / eps >= 0.70, f"eps={eps}: climax が {max(clim) / eps:.0%} 位置"


def test_climax_label_is_distinguished_from_plot_twist():
    """**『クライマックス前夜の衝撃』の部分文字列で『クライマックス』と判定しない**。

    既存テストの `"クライマックス" in instruction` は eps=300 で
    152..283 = 作品全体の 44% を指して偽陽性になっていた。
    """
    for eps in (20, 100, 300):
        hits = [e for e in range(1, eps + 1) if "クライマックス" in _label(e, eps)]
        window = [e for e in range(1, eps + 1) if _label(e, eps) == "クライマックス"]
        assert hits == window, f"eps={eps}: 部分文字列判定が偽陽性 {set(hits) - set(window)}"


def test_bounds_are_derived_from_story_spine_spans():
    """**境界が語彙 span から派生している**こと（二重管理の禁止）。"""
    v = BEAT_VOCABULARY
    assert PacingGraph._CLIMAX_END == v["climax"].span[1]
    assert PacingGraph._FIRST_EXPLOSION_START == v["first_win"].span[0]
    assert PacingGraph._HOOK_END == v["revelation"].span[1]
    assert PacingGraph._CLIMAX_START == v["last_stand"].span[0]


def test_no_episode_scaled_window_remains_in_source():
    """`1.0 - 2.0 / total_eps` のような話数比例窓がソースに残っていないこと。"""
    src = Path("src/backend/engine_narrative.py").read_text(encoding="utf-8")
    for banned in ("1.0 - 2.0 / total_eps", "1.0 - 2 / total_eps", "- 2.0 / total_eps"):
        assert banned not in src, f"絶対話数窓が残存: {banned}"
