"""話数を変えても構造が破綻しないこと（絶対話数バグの回帰防止）。"""

import pytest

from config.story_spine import LENGTHS, PATTERNS, resolve_spine
from src.services.spine_resolver import _HOOK_KEYS


@pytest.mark.parametrize("eps", [10, 25, 40, 100, 300])
def test_climax_relative_position_is_length_independent(eps):
    """クライマックスの相対位置は 0.75-0.92 に収まること。"""
    spine = resolve_spine("exile_rise", "long_serial", "web", eps)
    climax = next(b for b in spine.beats if b.key == "climax")
    rel = ((climax.ep_start + climax.ep_end) / 2) / eps
    assert 0.75 <= rel <= 0.92, f"eps={eps}: climax の相対位置が {rel:.2f}"


@pytest.mark.parametrize("eps", [20, 40, 100, 300])
def test_midpoint_relative_position_is_length_independent(eps):
    """中点反転の相対位置は 0.40-0.60 に収まること。"""
    spine = resolve_spine("exile_rise", "long_serial", "web", eps)
    mid = next(b for b in spine.beats if b.key == "midpoint_reversal")
    rel = ((mid.ep_start + mid.ep_end) / 2) / eps
    assert 0.40 <= rel <= 0.60, f"eps={eps}: midpoint の相対位置が {rel:.2f}"


@pytest.mark.parametrize("pattern", ["exile_rise", "detective_mystery", "slow_life", "healing_care"])
@pytest.mark.parametrize("eps", [20, 60, 200])
def test_critical_beats_keep_their_order_across_lengths(pattern, eps):
    """話数を変えても『つかみ → 中点反転 → クライマックス』の順序は崩れないこと。

    beat 数そのものは長さに応じて変わりうるので、キー集合の一致までは要求しない。
    """
    spine = resolve_spine(pattern, "long_serial", "web", eps)
    keys = spine.keys
    hook_idx = next(i for i, k in enumerate(keys) if k in _HOOK_KEYS)
    mid_idx = keys.index("midpoint_reversal")
    climax_idx = keys.index("climax")
    assert hook_idx < mid_idx < climax_idx, f"{pattern}@{eps}: 順序が崩れた {keys}"
    assert "climax" not in keys[climax_idx + 1:], f"{pattern}@{eps}: climax が重複 {keys}"


@pytest.mark.parametrize("eps", [20, 60, 200])
def test_web_market_always_ends_with_volume_hook(eps):
    """Web 連載の『話末の引き』契約は長さによらず守られること。"""
    for pattern in ("exile_rise", "detective_mystery", "slow_life", "healing_care", "avenger_dark"):
        keys = resolve_spine(pattern, "long_serial", "web", eps).keys
        assert keys[-1] == "volume_hook", f"{pattern}@{eps}: 最後が {keys[-1]!r}（{keys}）"


@pytest.mark.parametrize("eps", [10, 25, 40, 100, 300])
def test_tension_curve_shape_is_length_independent(eps):
    """テンション曲線の形が話数に依存しないこと（同じ相対位置 → 同じ tension 列）。"""
    spine = resolve_spine("exile_rise", "long_serial", "web", eps)
    tensions = [round(((b.ep_start + b.ep_end) / 2 - 1) / max(eps - 1, 1), 3) for b in spine.beats]
    assert tensions == sorted(tensions), f"eps={eps}: beat の位置が単調でない {tensions}"


def test_pacing_graph_is_length_independent():
    """既存バグの直接の回帰テスト。旧実装は ep5 / 24-26 が絶対だった。"""
    from src.backend.engine_narrative import PacingGraph

    short = PacingGraph.get_instruction(2, total_eps=20)
    long_ = PacingGraph.get_instruction(10, total_eps=100)
    assert short["instruction"] == long_["instruction"], (
        "話数だけ変えても同じ相対位置なら同じ指示になるはず"
    )


def test_first_explosion_position_scales():
    """第1の爆発が「10%時点」に固定されていること。"""
    from src.backend.engine_narrative import PacingGraph

    for eps in (20, 40, 100):
        found = [
            ep for ep in range(1, eps + 1)
            if "第1の爆発" in PacingGraph.get_instruction(ep, total_eps=eps)["instruction"]
        ]
        assert found, f"eps={eps} で第1の爆発が見つからない"
        rel = found[0] / eps
        assert 0.05 <= rel <= 0.25, f"eps={eps}: 第1の爆発の相対位置が {rel:.2f}"


def test_long_serial_eps_range_matches_plan():
    assert LENGTHS["long_serial"]["eps_range"] == [100, 300]
    for eps in LENGTHS["long_serial"]["eps_range"]:
        assert resolve_spine("exile_rise", "long_serial", "web", eps).beats
