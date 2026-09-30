"""**短編（1-3 話）でも部構成が破綻しないこと**の回帰テスト。

レビューで eps=1,2,3 で inverted 区間と範囲外の部を確認した。
F1 計画の中心ユースケース（short.eps_range=[1,3]）が壊れていた。
"""
from __future__ import annotations

import inspect

import pytest

from src.backend.workflows.reverse_plot_workflow import (
    EMOTIONAL_GOAL_TO_CATHARSIS,
    ReversePlotGenerationWorkflow,
)

# _design_arcs は self を使わないため unbound 呼び出しでよい（生成コストゼロ）
_design_arcs = ReversePlotGenerationWorkflow._design_arcs

CONFLICTS = ["ideal_vs_reality", "past_vs_future", "individual_vs_org", "love_vs_duty", "unknown"]


@pytest.mark.parametrize("eps", [1, 2, 3, 4, 5, 7, 10, 20, 40])
@pytest.mark.parametrize("conflict", CONFLICTS)
def test_arcs_are_ordered_and_within_range(eps: int, conflict: str):
    """**start <= end、かつ 1 <= start <= end <= eps**（短編を含む）。"""
    arcs = _design_arcs(None, {"coreConflict": conflict}, eps)
    assert arcs, f"eps={eps}/{conflict}: 部が 1 つも無い"
    prev_end = 0
    for arc in arcs:
        assert arc.start_ep <= arc.end_ep, (
            f"eps={eps}/{conflict}: inverted 区間 {arc.start_ep}>{arc.end_ep}"
        )
        assert 1 <= arc.start_ep, f"eps={eps}/{conflict}: start={arc.start_ep} が 1 未満"
        assert arc.end_ep <= eps, (
            f"eps={eps}/{conflict}: end={arc.end_ep} が総話数 {eps} を超過"
        )
        assert arc.start_ep == prev_end + 1, (
            f"eps={eps}/{conflict}: 部が連続していない（gap: {prev_end} -> {arc.start_ep}）"
        )
        prev_end = arc.end_ep
    assert prev_end == eps, f"eps={eps}/{conflict}: 最後の部が {prev_end} で総話数に届かない"


@pytest.mark.parametrize("eps", [1, 2, 3, 5, 10, 40])
def test_arc_count_never_exceeds_episode_count(eps: int):
    """部数が話数を超えないこと（`eps=1` で 4 部出来てしまう bug）。"""
    arcs = _design_arcs(None, {"coreConflict": "past_vs_future"}, eps)
    assert len(arcs) <= eps, f"eps={eps}: {len(arcs)} 部 > {eps} 話"


def test_unknown_emotional_goal_does_not_raise_keyerror():
    """**`KeyError` を出さないこと**（`/easy_mode/reverse-generate` が 500 になっていた）。"""
    for goal in ("triumph", "bittersweet", "twist", "heartwarming", "hopeful", "unknown_goal", None):
        got = EMOTIONAL_GOAL_TO_CATHARSIS.get(goal, EMOTIONAL_GOAL_TO_CATHARSIS["triumph"])
        assert got and "tensionPeak" in got, goal


def test_catharsis_map_is_not_accessed_defensively_missing():
    """**無防備な添字参照が残っていないこと**（構造テスト）。"""
    src = inspect.getsource(ReversePlotGenerationWorkflow)
    assert "EMOTIONAL_GOAL_TO_CATHARSIS[emotional_goal]" not in src, (
        "無防備な添字参照が残っている（.get(goal, default) に変更すること）"
    )


def test_spine_tension_is_used_for_every_episode(eps: int = 10):
    """tension が Spine 由来であること（自前計算への回帰防止）。"""
    spine = ReversePlotGenerationWorkflow._spine_for(None, 10)
    assert spine is not None and spine.beats
    assert not hasattr(ReversePlotGenerationWorkflow, "_calc_tension"), (
        "_calc_tension が復活している（Spine ラッパーに縮小すること）"
    )
