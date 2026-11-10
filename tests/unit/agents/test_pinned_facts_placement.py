"""プロンプト内の pinned_head / pinned_tail 位置不変テスト (PLAN_M1 Step 18).

Lost in the Middle 対策として、重要事実がプロンプトの「先頭側」と
「末尾側」に配置されることを検証する。また、既存ブロックの相対順序が
変更されていないことも併せて検証する（既存構造のリグレッション防止）。
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
import pytest

from prompts.manager import PromptManager

HEAD_MARKER = "【最重要の確定事実・必守事項】"
TAIL_MARKER = "【執筆直前の再確認】"
WORK_CONTEXT_MARKER = "【作品文脈】"
TARGET_WORD_COUNT_MARKER = "■ 目標文字数"
OUTPUT_FORMAT_MARKER = "--- 出力形式 ---"
LAYER3_MARKER = "【Layer3: 直前エピソードの原文】"


def _build_manager() -> PromptManager:
    return PromptManager(jinja_env=Environment(loader=FileSystemLoader("prompts")))


async def _render_prompt(
    manager: PromptManager,
    pinned_head: str,
    pinned_tail: str,
    three_layer_ctx: str = "",
) -> str:
    """指定の pinned_head/tail でプロンプトをレンダリングする。"""
    return await manager.build_final_writing_prompt(
        ep_num=1,
        plot_data={
            "scenes": [],
            "current_chain_phase": "Hate",
            "detailed_blueprint": "",
        },
        script_text="",
        target_word_count=2000,
        book_id=None,
        char_static_ctx="テストキャラクター設定",
        char_dynamic_ctx="テスト動的状態",
        prev_ctx="テスト前文脈",
        pov_character_name="テスト主人公",
        dialogue_profiles={},
        density_level="Standard",
        style_tag=None,
        foreshadowing_context="",
        contract_foreshadowings=[],
        unresolved_foreshadowings=[],
        emotional_context="",
        rag_context_block="",
        pinned_head=pinned_head,
        pinned_tail=pinned_tail,
        quota_inst="",
        show_tell_inst="",
        forbidden_inst="",
        hook_inst="",
        assertion_inst="",
        blueprint="",
        tone_inst="",
        three_layer_ctx=three_layer_ctx,
    )


class TestPinnedFactsPlacementFlagOff:
    """flag off 時（pinned_head/tail 空）の位置テスト。"""

    @pytest.mark.asyncio
    async def test_head_block_absent_when_off(self):
        """pinned_head が空なら head ブロックは出力されない。"""
        manager = _build_manager()
        prompt = await _render_prompt(manager, pinned_head="", pinned_tail="")
        assert HEAD_MARKER not in prompt

    @pytest.mark.asyncio
    async def test_tail_block_absent_when_off(self):
        """pinned_tail が空なら tail ブロックは出力されない。"""
        manager = _build_manager()
        prompt = await _render_prompt(manager, pinned_head="", pinned_tail="")
        assert TAIL_MARKER not in prompt


class TestPinnedFactsPlacementFlagOn:
    """flag on 時（pinned_head/tail 有値）の位置テスト。"""

    @pytest.mark.asyncio
    async def test_head_is_before_work_context(self):
        """head ブロックが【作品文脈】より前（先頭側）にある。"""
        manager = _build_manager()
        prompt = await _render_prompt(
            manager,
            pinned_head="- 【期限超過】竜の鱗の行方 の回収が未完了",
            pinned_tail="",
        )
        idx_head = prompt.index(HEAD_MARKER)
        idx_work = prompt.index(WORK_CONTEXT_MARKER)
        assert idx_head < idx_work, (
            f"head ({idx_head}) should be before work_context ({idx_work})"
        )

    @pytest.mark.asyncio
    async def test_tail_is_after_target_word_count_and_before_output_format(self):
        """tail ブロックが【目標文字数】より後、かつ【出力形式】より前にある。"""
        manager = _build_manager()
        prompt = await _render_prompt(
            manager,
            pinned_head="",
            pinned_tail="☐ 【本話回収必須】古代の封印",
        )
        idx_tail = prompt.index(TAIL_MARKER)
        idx_target = prompt.index(TARGET_WORD_COUNT_MARKER)
        idx_output = prompt.index(OUTPUT_FORMAT_MARKER)
        assert idx_target < idx_tail < idx_output, (
            f"tail ({idx_tail}) should be between target_word_count ({idx_target}) "
            f"and output_format ({idx_output})"
        )

    @pytest.mark.asyncio
    async def test_existing_block_order_preserved(self):
        """既存3層ブロックの相対順序が変更されていない。

        順序: 不変属性(char_static_ctx) → 既知の文脈(prev_ctx) → Layer3(three_layer_ctx)
        """
        manager = _build_manager()
        three_layer_ctx = (
            "【Layer1: 世界観・キャラクター設定（不変）】\nテストLayer1\n\n"
            "【Layer2: 過去の確定事実タイムライン】\nテストLayer2\n\n"
            "【Layer3: 直前エピソードの原文】\nテストLayer3"
        )
        prompt = await _render_prompt(
            manager,
            pinned_head="- テストhead",
            pinned_tail="☐ テストtail",
            three_layer_ctx=three_layer_ctx,
        )

        idx_static = prompt.index("不変属性:")
        idx_prev = prompt.index("既知の文脈:")
        idx_layer3 = prompt.index(LAYER3_MARKER)

        assert idx_static < idx_prev < idx_layer3, (
            f"block order broken: static={idx_static}, prev={idx_prev}, "
            f"layer3={idx_layer3}"
        )

    @pytest.mark.asyncio
    async def test_head_and_tail_coexist(self):
        """head と tail が同時に設定できる。"""
        manager = _build_manager()
        prompt = await _render_prompt(
            manager,
            pinned_head="- 【期限超過】テスト伏線 の回収が未完了",
            pinned_tail="☐ 【本話回収必須】テスト伏線",
        )
        assert HEAD_MARKER in prompt
        assert TAIL_MARKER in prompt
        idx_head = prompt.index(HEAD_MARKER)
        idx_tail = prompt.index(TAIL_MARKER)
        assert idx_head < idx_tail, "head should be before tail"
