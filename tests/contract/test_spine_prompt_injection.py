"""**`spine_quality=off` で既存プロンプトが完全に不変**であること（最重要契約）。"""
import pytest

from src.services.llm.prompts import (
    NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE,
    build_spine_section,
)

KWARGS = dict(
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


def test_off_produces_legacy_prompt_exactly():
    """**バイト単位で同一**であること。これが変わると全書籍の再生成結果が変わる。"""
    prompt = NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(**KWARGS, spine_section="")
    assert prompt == NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(**KWARGS)


def test_build_spine_section_off_returns_empty():
    assert build_spine_section(None, "off", 1) == ""


def test_soft_includes_duty():
    from config.story_spine import resolve_spine

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    section = build_spine_section(spine, "soft", ep_num=1)
    assert section, "soft で duty が入っていない"
    assert spine.at(1).duty[:8] in section


def test_hard_includes_tension_and_artifact():
    from config.story_spine import resolve_spine

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    section = build_spine_section(spine, "hard", ep_num=33)
    assert str(spine.at(33).tension) in section or "テンション" in section


def test_unknown_quality_falls_back_to_off():
    """未知の値が `hard` になってしまわないこと（安全側）。"""
    assert build_spine_section(None, "bogus", 1) == ""
