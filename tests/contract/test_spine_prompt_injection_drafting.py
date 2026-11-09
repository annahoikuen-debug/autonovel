"""**`spine_quality=off` で drafting 経路のプロンプトが完全に不変**であること。

壊れ方: build_drafting_prompt が off でも spine セクションを連結する /
spine あり・soft/hard で注入漏れ → この契約が赤になる。
"""

from __future__ import annotations

import pytest

from config.story_spine import resolve_spine
from prompts.manager import PromptManager


@pytest.fixture
def pm():
    return PromptManager()


@pytest.fixture
def base_kwargs():
    return dict(
        ep_num=1,
        plot_data={"scenes": [], "current_chain_phase": "Hate", "detailed_blueprint": ""},
        script_text="",
        target_word_count=3000,
        char_static_ctx="",
        char_dynamic_ctx="",
        prev_ctx="",
    )


@pytest.mark.asyncio
async def test_off_byte_identical_drafting_prompt(pm, base_kwargs):
    """spine_quality=off（既定）で、spine 解決の有無に関わらず
    build_drafting_prompt の出力がバイト単位で同一であること。
    """
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)

    _sys_a, user_a = await pm.build_drafting_prompt(**base_kwargs, spine=None, spine_quality="off")
    _sys_b, user_b = await pm.build_drafting_prompt(
        **base_kwargs, spine=spine, spine_quality="off"
    )
    assert user_a == user_b, "off でも spine オブジェクトありで出力が変わった"


@pytest.mark.asyncio
async def test_off_with_spine_object_is_still_byte_identical(pm, base_kwargs):
    """spine オブジェクトが渡されていても off なら空文字連結であること
    （build_spine_section の off 短絡に依存）。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    _, user = await pm.build_drafting_prompt(**base_kwargs, spine=spine, spine_quality="off")
    _, user_no_spine = await pm.build_drafting_prompt(**base_kwargs, spine=None, spine_quality="off")
    assert user == user_no_spine


@pytest.mark.asyncio
async def test_soft_injects_reference_and_hard_injects_duty(pm, base_kwargs):
    """soft: 「【構造の参考】」ラベル＋duty。
    hard: 「【この話で必ず果たすこと】」ラベル＋テンション＋duty。
    off: 空文字。3レベルの差分を確認。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    _sys_off, user_off = await pm.build_drafting_prompt(**base_kwargs, spine=spine, spine_quality="off")
    _sys_soft, user_soft = await pm.build_drafting_prompt(**base_kwargs, spine=spine, spine_quality="soft")
    _sys_hard, user_hard = await pm.build_drafting_prompt(**base_kwargs, spine=spine, spine_quality="hard")

    assert user_soft != user_off, "soft で注入されていない"
    assert user_hard != user_off, "hard で注入されていない"
    assert user_soft != user_hard, "soft と hard が同一"
    assert "【構造の参考】" in user_soft
    assert "【この話で必ず果たすこと】" in user_hard


@pytest.mark.asyncio
async def test_ep_num_beat_mapping_respected(pm, base_kwargs):
    """ep_num=1 と ep_num=20 で異なるビートが注入されること
    （spine.at(ep_num) の話数→ビート対応の回帰）。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    _sys_ep1, user_ep1 = await pm.build_drafting_prompt(
        **{**base_kwargs, "ep_num": 1}, spine=spine, spine_quality="hard"
    )
    _sys_ep20, user_ep20 = await pm.build_drafting_prompt(
        **{**base_kwargs, "ep_num": 20}, spine=spine, spine_quality="hard"
    )
    assert user_ep1 != user_ep20, "ep_num によって注入ビートが変わっていない"


@pytest.mark.asyncio
async def test_exception_in_at_falls_back_to_empty(pm, base_kwargs):
    """spine.at() が例外を投げても空文字に倒れ、プロンプト生成自体は
    壊れないこと（fail-open）。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)

    class BrokenSpine:
        def at(self, ep_num):
            raise RuntimeError("broken at")

    _sys_broken, user_broken = await pm.build_drafting_prompt(
        **base_kwargs, spine=BrokenSpine(), spine_quality="hard"
    )
    _sys_none, user_none = await pm.build_drafting_prompt(**base_kwargs, spine=None, spine_quality="hard")
    assert user_broken == user_none, "spine.at() 例外でプロンプトが壊れた"
