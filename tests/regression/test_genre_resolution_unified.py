"""**4系統のジャンル語彙の統合**に対する回帰テスト。"""
import pytest

from src.backend.routers.easy_mode import resolve_genre_to_preset

# 旧 G1: SimpleModePanel.tsx:91-103
LEGACY_UI_VALUES = ["fan", "sf", "romance", "mystery", "horror", "other"]
# 旧 G2: constants/genres.ts:10-18
LEGACY_CONSTANTS_VALUES = [
    "ハイファンタジー (R15)", "ダークファンタジー (R15)", "異世界転生・バトル (R15)",
    "ざまぁ・追放・無双 (R15)", "悪役令嬢・婚約破棄", "追放後スローライフ", "VRMMO・ゲーム世界",
]
# 旧 G3: Step1PlotInput.tsx:132-136
LEGACY_WIZARD_VALUES = ["fantasy", "modern_fantasy", "romance", "scifi"]
# 旧 G4: archetypes_new.py:476
LEGACY_ARCHETYPE_VALUES = ["ファンタジー", "SF", "現代", "歴史", "官能/ロマンス", "その他"]


@pytest.mark.parametrize("value", LEGACY_UI_VALUES)
def test_simple_mode_values_now_resolve(value):
    """**旧バグの直接の回帰テスト**。旧実装は 'fan' 等で None を返していた。"""
    assert resolve_genre_to_preset(value) is not None, f"{value!r} が None のまま"


@pytest.mark.parametrize("value", LEGACY_CONSTANTS_VALUES + LEGACY_WIZARD_VALUES
                         + LEGACY_ARCHETYPE_VALUES)
def test_all_legacy_vocabularies_resolve(value):
    assert resolve_genre_to_preset(value) is not None, f"{value!r} が解決しない"


def test_legacy_keyword_priority_is_preserved():
    """既存の11キーワードが同じ preset を返すこと（文言の意味が変わっていない）。"""
    expectations = {
        "ざまぁ": "zarma", "令嬢": "aku_reijo", "VRMMO": "vrmmo",
        "ダンジョン": "dungeon_admin", "スローライフ": "slow_life",
        "追放": "slow_life", "ループ": "loop", "テンセイ": "cheat_tensei",
        "現代チート": "modern_cheat", "異世界転生": "cheat_tensei",
        "ダークファンタジー": "cheat_tensei",
    }
    for keyword, preset in expectations.items():
        assert resolve_genre_to_preset(keyword) == preset, (
            f"{keyword!r} の解決先が {resolve_genre_to_preset(keyword)!r} に変わった"
        )


def test_empty_string_still_returns_none():
    """空文字は None のまま（サイレントなデフォルト代入をしない）。"""
    assert resolve_genre_to_preset("") is None
    assert resolve_genre_to_preset(None) is None


def test_unknown_garbage_returns_none():
    assert resolve_genre_to_preset("ZZZ存在しないZZZ") is None
