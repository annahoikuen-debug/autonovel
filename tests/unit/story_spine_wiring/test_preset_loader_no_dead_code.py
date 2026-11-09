"""H1（get_plot_pattern 削除）の回帰テスト。

壊れ方: 削除漏れ・他機能の偶発破壊 → 赤。
"""

from __future__ import annotations

import pytest

import src.services.preset_loader as preset_loader


def test_get_plot_pattern_is_gone():
    """preset_loader に get_plot_pattern が存在しないこと（H1 で削除済み）。"""
    assert not hasattr(preset_loader, "get_plot_pattern")


def test_preset_loader_public_api_intact():
    """load_preset_for_pipeline / get_tension_curve が
    従来どおり動くこと（削除の副作用ゼロ）。"""
    assert callable(preset_loader.load_preset_for_pipeline)
    assert callable(preset_loader.get_tension_curve)

    # 全ジャンルで load_preset_for_pipeline が例外なく動くこと（archetype_key には pattern_key を渡す）
    for genre in ["zarma", "aku_reijo", "cheat_tensei", "slow_life", "dungeon_admin", "modern_cheat", "ts_tensei", "vrmmo", "loop"]:
        preset = preset_loader.load_preset_for_pipeline(genre, "exile_rise")
        assert isinstance(preset, dict)
        assert "_meta" in preset

    # get_tension_curve が dict を返すこと（preset_dict を受け取る）
    preset = preset_loader.load_preset_for_pipeline("zarma", "exile_rise")
    tension = preset_loader.get_tension_curve(preset)
    assert isinstance(tension, dict)

def test_no_call_sites_remain():
    """src/ tests/ 全体をスキャンし get_plot_pattern の参照が 0 件であること。
    （本テストファイル自身の「get_plot_pattern」文字列は除外する。）"""
    from pathlib import Path

    roots = [Path("src"), Path("tests")]
    this_file = Path(__file__).resolve()
    count = 0
    for root in roots:
        for p in root.rglob("*.py"):
            if p.resolve() == this_file:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "get_plot_pattern" in text:
                count += 1
    assert count == 0, f"get_plot_pattern の参照が {count} 件残っています"
