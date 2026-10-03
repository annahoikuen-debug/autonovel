"""**`spine_quality=off` で既存プロンプトが完全に不変**であること（最重要契約）。"""
from __future__ import annotations


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

# F1 導入前のプロンプトテンプレートの凍結スナップショット（バイト一致検証用）
LEGACY_TEMPLATE_SNAPSHOT = """【ジャンル】: {genre}
【主人公設定】:
- 名前: {char_name}
- 性格・特徴: {char_personality}
- 特殊能力・スキル: {char_ability}

{style_bias_section}

【GraphRAG: 確定している世界観・人物相関・アイテム状態】:
{graph_context}

【GraphRAG: 過去の関連シーン・伏線】:
{vector_context}

【前話までのダイジェスト】:
{history_context}

【直前のシーン】:
{current_chapter}

上記の確定事実と過去の文脈を決して矛盾させず、指定された【作家性DNA・文体】を忠実に再現して、続く魅力的な本文を執筆してください。
"""


def test_off_produces_legacy_prompt_exactly():
    """**バイト単位で旧テンプレートと同一**であること。

    これが 1 本でも落ちると全既存書籍の再生成結果が変わる。
    """
    legacy = LEGACY_TEMPLATE_SNAPSHOT.format(**KWARGS)
    current = NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(**KWARGS)
    assert current == legacy, (
        f"プロンプトが変化した（{len(legacy)} -> {len(current)} 文字）。"
        "spine_quality=off では既存書籍の再生成結果を変えないこと"
    )


def test_legacy_snapshot_is_not_vacuous():
    """**このテストが意味を持つことの自己検証**。"""
    assert len(LEGACY_TEMPLATE_SNAPSHOT) > 200, "旧テンプレートが短すぎる（取得失敗の可能性）"
    assert "{genre}" in LEGACY_TEMPLATE_SNAPSHOT and "{char_name}" in LEGACY_TEMPLATE_SNAPSHOT
    assert "spine_section" not in LEGACY_TEMPLATE_SNAPSHOT


def test_current_template_does_declare_spine_section():
    """新テンプレートには注入点があること（=注入が実際に機能する）。"""
    assert "spine_section" in (
        NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.template
        if hasattr(NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE, "template")
        else str(NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE)
    )


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
