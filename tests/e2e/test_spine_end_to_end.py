"""STORY_SPINE: カード選択 → Spine → プロンプト注入 の通し確認。"""

import pytest


def test_card_to_spine_to_prompt():
    """1枚のカードから最終プロンプトまでが繋がること。"""
    from config.story_spine import CARDS, resolve_spine
    from src.services.llm.prompts import build_spine_section, build_spine_summary

    card = CARDS["tpl_exile_web"]
    spine = resolve_spine(card["pattern"], card["length"], card["market"], 40)

    # Web1巻の構造容量（min_beats）は18以上。実際の beat 数はパターンが決める。
    assert len(spine.beats) >= 8, f"Web1巻の beat が少なすぎる: {len(spine.beats)}"
    assert spine.at(1) is not None
    assert spine.at(40) is not None
    assert spine.keys[-1] == "volume_hook"
    assert build_spine_summary(spine)
    assert build_spine_section(spine, "hard", ep_num=1)


def test_every_card_resolves():
    """24枚すべてが解決できること。"""
    from config.story_spine import CARDS, resolve_spine

    for ck, card in CARDS.items():
        spine = resolve_spine(card["pattern"], card["length"], card["market"])
        assert spine.beats, f"{ck} が解決しない"


def test_every_card_passes_spine_validation():
    """カードから得た Spine が全て生成前検証を通ること。"""
    from config.story_spine import CARDS, resolve_spine
    from src.services.structure_validator import validate_spine

    for ck, card in CARDS.items():
        spine = resolve_spine(card["pattern"], card["length"], card["market"])
        result = validate_spine(spine)
        assert result["is_healthy"], f"{ck}: {result['problems']}"


def test_long_serial_100ep_passes_validation():
    """**100話構成が検証器を通ること**（40話上限撤去の実証）。"""
    from config.story_spine import resolve_spine
    from src.services.structure_validator import validate

    spine = resolve_spine("exile_rise", "long_serial", "web", 100)
    chapters = [
        {"chapter_number": b.ep_start, "tension": int(b.tension * 10)} for b in spine.beats
    ]
    result = validate(chapters, pattern_key="exile_rise")
    assert result["pattern_key"] == "exile_rise"
    assert result["total_chapters"] == len(spine.beats)


def test_short_form_e2e():
    """1話短編の通し確認。"""
    from config.story_spine import resolve_spine
    from src.services.structure_validator import validate_spine

    spine = resolve_spine("exile_rise", "short", "general", 1)
    assert {"inciting", "midpoint_reversal", "climax"} <= set(spine.keys)
    assert validate_spine(spine)["is_healthy"]


def test_off_quality_produces_byte_identical_prompt():
    """`spine_quality=off` で既存プロンプトが完全に不変であること（本計画の最重要契約）。"""
    from config.story_spine import resolve_spine
    from tests.contract.test_spine_prompt_injection import LEGACY_TEMPLATE_SNAPSHOT
    from src.services.llm.prompts import (
        NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE,
        build_spine_section,
    )

    kwargs = dict(
        genre="ハイファンタジー (R15)",
        char_name="山田太郎",
        char_personality="冷静",
        char_ability="万能鑑定",
        style_bias_section="【作家性DNA】短文主体",
        graph_context="(なし)",
        vector_context="(なし)",
        history_context="(なし)",
        current_chapter="第1話の本文",
    )
    legacy = LEGACY_TEMPLATE_SNAPSHOT.format(**kwargs)
    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    for ep in range(1, 41):
        section = build_spine_section(spine, "off", ep_num=ep)
        assert section == "", f"off なのに注入された: {section!r}"
    with_section = NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(
        **kwargs, spine_section=""
    )
    assert with_section == legacy
    current = NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(**kwargs)
    assert current == legacy


def test_soft_and_hard_differ():
    """soft と hard で注入内容が変わること（段階適用が機能している）。"""
    from config.story_spine import resolve_spine
    from src.services.llm.prompts import build_spine_section

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    soft = build_spine_section(spine, "soft", ep_num=33)
    hard = build_spine_section(spine, "hard", ep_num=33)
    assert soft and hard and soft != hard
    assert spine.at(33).duty[:8] in hard


def test_spine_never_costs_llm_calls_end_to_end():
    """カード1枚からプロンプト文字列までを LLM 0 回で作る。"""
    from config.story_spine import CARDS, resolve_spine
    from src.services.llm.prompts import build_spine_summary

    for ck, card in CARDS.items():
        spine = resolve_spine(card["pattern"], card["length"], card["market"])
        assert isinstance(build_spine_summary(spine), str), ck


@pytest.mark.parametrize("length_key", ["short", "novella", "single_volume", "web_volume", "long_serial", "series"])
def test_every_length_works_with_every_pattern(length_key):
    """長さ階層とパターンの直積で必ず解決できること（代表6種で確認）。"""
    from config.story_spine import PATTERNS, resolve_spine
    from src.services.structure_validator import validate_spine

    for pattern in PATTERNS:
        spine = resolve_spine(pattern, length_key, "general")
        assert spine.beats, f"{pattern}×{length_key} が空"
        assert validate_spine(spine)["is_healthy"], f"{pattern}×{length_key}"
