"""短期ホライズン丸め／アンカー吸着が既存不変条件を壊さないことの回帰テスト（PLAN_W5 Step 3-4）。"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.services.foreshadowing.anchors import anchor_episode  # noqa: E402
from src.services.foreshadowing.planner import (  # noqa: E402
    SHORT_TERM_HORIZON,
    plan_foreshadowing,
)

MID = anchor_episode("midpoint")
CLIMAX = anchor_episode("climax")


# ── Step 3: 短期ホライズン ────────────────────────────────────────
def test_default_behavior_unchanged_without_flag(monkeypatch):
    """フラグ無しで呼んだ結果は既存テストと同一であること（回帰の最重要点）。"""
    monkeypatch.delenv("FORESHADOW_SHORT_HORIZON", raising=False)
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=40)
        assert plan.target_episode > planted, planted
        assert plan.horizon >= 1, planted


def test_short_horizon_clamps_to_3():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=40, use_short_term_horizon=True)
        assert planted < plan.target_episode <= planted + SHORT_TERM_HORIZON, planted


def test_short_horizon_never_produces_horizon_zero():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=planted, use_short_term_horizon=True)
        assert plan.horizon >= 1, planted


def test_short_horizon_never_exceeds_total():
    """`planted < total` の範囲では回収先が作品内に収まること。

    `planted == total`（最終話への設置）は既存仕様どおり `planted + 1`（作品外）を返し、
    `get_overdue` / KPI 側で「期限超過」に可視化されるため、**この範囲外**。
    """
    for planted in range(1, 40):
        plan = plan_foreshadowing(
            planted, total_episodes=min(planted + 1, 40), use_short_term_horizon=True
        )
        assert plan.target_episode <= min(planted + 1, 40), planted


def test_short_horizon_flag_env_enables(monkeypatch):
    monkeypatch.setenv("FORESHADOW_SHORT_HORIZON", "1")
    plan = plan_foreshadowing(1, total_episodes=40)
    assert plan.target_episode <= 1 + SHORT_TERM_HORIZON


# ── Step 4: アンカー吸着 ──────────────────────────────────────────
def test_anchor_snap_off_is_bitwise_unchanged(monkeypatch):
    monkeypatch.delenv("FORESHADOW_ANCHOR_SNAP", raising=False)
    for planted in range(1, 41):
        a = plan_foreshadowing(planted, total_episodes=40)
        b = plan_foreshadowing(planted, total_episodes=40, anchor_snap=False)
        assert a == b, planted


def test_anchor_snap_preserves_horizon_invariant():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=40, anchor_snap=True)
        assert plan.target_episode > planted, planted
        assert plan.horizon >= 1, planted


def test_anchor_snap_never_moves_forward():
    """前倒しはしない（= max）。元の算出値より大きく前早了値は出ない。"""
    for planted in range(1, 41):
        plain = plan_foreshadowing(planted, total_episodes=40)
        snapped = plan_foreshadowing(planted, total_episodes=40, anchor_snap=True)
        assert snapped.target_episode >= plain.target_episode, planted
        assert snapped.target_episode <= max(40, planted + 1), planted


def test_anchor_snap_respects_total_episodes():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=planted + 1, anchor_snap=True)
        assert plan.target_episode <= planted + 1, planted


def test_climax_is_the_last_payoff_anchor():
    assert CLIMAX > MID


def test_anchor_snap_flag_env_enables(monkeypatch):
    monkeypatch.setenv("FORESHADOW_ANCHOR_SNAP", "1")
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=40)
        assert plan.target_episode > planted
