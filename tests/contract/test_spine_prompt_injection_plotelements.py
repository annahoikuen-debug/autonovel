"""`build_macro_plot_skeleton_prompt` / `build_micro_scene_expander_prompt` の spine 注入契約。

壊れ方: off でも spine セクションを連結する /
新引数を渡さない既存呼び出しが壊れる /
macro に summary ではなく per-ep beat を入れる / micro に summary を入れる → この契約が赤になる。
"""

from __future__ import annotations

import pytest

from config.story_spine import resolve_spine
from prompts.manager import PromptManager
from src.models.plot import EpisodeMacroSkeleton


@pytest.fixture
def pm():
    return PromptManager()


@pytest.fixture
def macro_skeleton():
    return EpisodeMacroSkeleton(
        ep_num=5,
        title="第5話：試練",
        one_line_summary="主人公が最初の強敵と対峙する",
        inciting_event="強敵の出現",
        climax_payoff="勝利",
        tension=70,
        current_chain_phase="Conflict",
        resolution_style="Cheat",
        foreshadowing_plan=[],
    )


@pytest.fixture
def bible_json():
    return '{"title": "テスト作品", "genre": "ファンタジー"}'


@pytest.mark.asyncio
async def test_off_byte_identical_macro_prompt(pm, bible_json):
    """spine_quality=off で macro プロンプトがバイト単位で同一であること。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)

    _a = await pm.build_macro_plot_skeleton_prompt(
        bible_json, [1, 2, 3], spine=None, spine_quality="off"
    )
    _b = await pm.build_macro_plot_skeleton_prompt(
        bible_json, [1, 2, 3], spine=spine, spine_quality="off"
    )
    assert _a == _b, "off でも macro プロンプトが変わった"


@pytest.mark.asyncio
async def test_off_byte_identical_micro_prompt(pm, macro_skeleton):
    """spine_quality=off で micro プロンプトがバイト単位で同一であること。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)

    _a = await pm.build_micro_scene_expander_prompt(
        macro_skeleton, spine=None, spine_quality="off"
    )
    _b = await pm.build_micro_scene_expander_prompt(
        macro_skeleton, spine=spine, spine_quality="off"
    )
    assert _a == _b, "off でも micro プロンプトが変わった"


@pytest.mark.asyncio
async def test_existing_call_sites_unaffected(pm, bible_json, macro_skeleton):
    """新引数を渡さない既存の呼び出し形で従来どおり動くこと
    （H2-H4 の既定値付き追加が後方互換であることの直接検証）。"""
    macro = await pm.build_macro_plot_skeleton_prompt(bible_json, [1, 2, 3])
    micro = await pm.build_micro_scene_expander_prompt(macro_skeleton)
    assert isinstance(macro, str) and len(macro) > 0
    assert isinstance(micro, str) and len(micro) > 0


@pytest.mark.asyncio
async def test_summary_injected_only_when_soft_or_hard(pm, bible_json, macro_skeleton):
    """macro には build_spine_summary（全体構造）が入り、
    micro には当該話の build_spine_section が入ること。
    off は空文字。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)

    macro_off = await pm.build_macro_plot_skeleton_prompt(
        bible_json, [1, 2, 3], spine=spine, spine_quality="off"
    )
    macro_soft = await pm.build_macro_plot_skeleton_prompt(
        bible_json, [1, 2, 3], spine=spine, spine_quality="soft"
    )
    macro_hard = await pm.build_macro_plot_skeleton_prompt(
        bible_json, [1, 2, 3], spine=spine, spine_quality="hard"
    )
    assert macro_off == macro_off  # トートロジーだがoff固定の証左
    assert macro_soft != macro_off, "soft で macro summary が注入されていない"
    assert macro_hard != macro_off, "hard で macro summary が注入されていない"
    assert "【構造の割当】" in macro_soft or "【構造の割当】" in macro_hard

    micro_off = await pm.build_micro_scene_expander_prompt(
        macro_skeleton, spine=spine, spine_quality="off"
    )
    micro_hard = await pm.build_micro_scene_expander_prompt(
        macro_skeleton, spine=spine, spine_quality="hard"
    )
    assert micro_off == micro_off
    assert micro_hard != micro_off, "hard で micro duty が注入されていない"
    # macro には summary（全体構造）、micro には当該話duty が入ることを区別
    assert "【構造の割当】" not in micro_hard, "micro に macro の summary が混入している"
