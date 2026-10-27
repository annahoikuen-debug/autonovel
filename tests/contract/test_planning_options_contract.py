"""/api/config/planning_options の**レスポンス形状**を固定する契約テスト。

レビューで「FE のモックが実 API 形状を偽造していた」ことが
カード選択ハイライト無効・成長曲線混入の直接の原因だった。
**サーバーが返す形を Python 側で固定**し、FE 側はこれに合わせて修正する。
"""
from __future__ import annotations

import json

import pytest

from config.archetypes_new import STORY_ARCHETYPES
from config.story_spine import CARDS, LENGTHS, MARKETS, PATTERNS
from config.story_spine.beat import BEAT_VOCABULARY
from src.backend.routers.misc import get_planning_options


@pytest.fixture
async def opts():
    return await get_planning_options()


async def test_response_is_json_serializable(opts):
    """**生 YAML dict をそのまま返して 500 にならないこと**。"""
    payload = json.dumps(opts, ensure_ascii=False)
    assert len(payload) > 1000
    json.loads(payload)  # 往復可能


async def test_cards_expose_card_id_matching_yaml_key(opts):
    """**各カードが `card_id` を持つ**（FE の選択判定の前提）。"""
    cards = opts["cards"]
    assert isinstance(cards, list), "cards は list であるべき（dict だと FE が key を取り損なう）"
    assert len(cards) == len(CARDS) == 24, len(cards)
    for item in cards:
        assert "card_id" in item, f"card_id が無い: {item}"
        assert item["card_id"] in CARDS, item["card_id"]
        # カードの中身は YAML と一致していること（二重定義を作らない）
        assert item["label"] == CARDS[item["card_id"]]["label"]
        assert item["pattern"] == CARDS[item["card_id"]]["pattern"]
    assert len({c["card_id"] for c in cards}) == len(cards), "card_id が重複している"


async def test_growth_curves_is_present_and_non_empty(opts):
    """`growth_curves` が存在し、空でないこと（FE の select の唯一の供給元）。"""
    assert "growth_curves" in opts, "growth_curves が無い（FE は story_archetypes に墜ちる）"
    curves = opts["growth_curves"]
    values = list(curves.values()) if isinstance(curves, dict) else list(curves)
    assert values, "growth_curves が空"
    assert all(isinstance(v, str) and v for v in values), values


async def test_growth_curves_values_are_subset_of_story_archetypes(opts):
    """**保存先カラムと値集合が一致すること**（`plots.py` が受け付ける値だけを出す）。"""
    valid_curves = {
        v.get("growth_curve")
        for v in STORY_ARCHETYPES.values()
        if isinstance(v, dict) and "growth_curve" in v
    }
    curves = opts.get("growth_curves", [])
    values = list(curves.values()) if isinstance(curves, dict) else list(curves)
    assert set(values) <= valid_curves, (
        "STORY_ARCHETYPES に無い値が混ざっている（保存時に FK/ENUM で落ちる）"
    )


async def test_legacy_keys_are_preserved(opts):
    """既存 FE が使っているキーは削除しないこと（後方互換）。"""
    for key in ("easy_genres", "story_archetypes", "style_definitions"):
        assert key in opts, f"既存キー {key} が消えている"
    for key in ("cards", "lengths", "markets", "patterns", "genres", "beat_vocabulary"):
        assert key in opts, f"STORY_SPINE キー {key} が無い"


async def test_beat_vocabulary_is_complete_and_flat(opts):
    """beat_vocabulary が 34 語で span がリスト化されていること。"""
    bv = opts["beat_vocabulary"]
    assert len(bv) == len(BEAT_VOCABULARY) >= 30, len(bv)
    for key, item in bv.items():
        assert item["key"] == key
        assert isinstance(item["span"], list) and len(item["span"]) == 2, item
        assert 0.0 <= item["span"][0] < item["span"][1] <= 1.0, item


async def test_endpoints_tables_have_expected_sizes(opts):
    assert len(opts["lengths"]) == len(LENGTHS) == 6
    assert len(opts["markets"]) == len(MARKETS) == 4
    assert len(opts["patterns"]) == len(PATTERNS) == 38
