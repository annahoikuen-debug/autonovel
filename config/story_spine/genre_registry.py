"""GENRE_REGISTRY: 旧4系統（G1-G4）のジャンル語彙を1書に統合する単一レジストリ。

所有: TRACK-B（B1/B2/B3）。
このモジュールは `config/story_spine` の他ファイル（beat.py / loader.py）を変更しない。

背景:
- 旧4系統のジャンル語彙がそれぞれ別のファイルにハードコードされていた
  （G1 SimpleModePanel.tsx / G2 constants/genres.ts / G3 Step1PlotInput.tsx / G4 archetypes_new.py）。
- genre→preset 表も3系統（easy_mode / preset_loader / spice_guard_adapter）に分散していた。

本モジュールを唯一の解決点とし、各レイヤーはここへ委譲する。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "GENRE_REGISTRY",
    "LEGACY_KEYWORD_PRIORITY",
    "genre_payload",
    "resolve_genre",
    "resolve_preset_key",
]


# 1エントリ = 1つの正規ジャンル。旧4系統の値はすべて aliases に集約し、1つも漏らさない。
# preset_key は旧3表を一本化した値（src/presets/loader.py の SUPPORTED_GENRES を優先）。
GENRE_REGISTRY: dict[str, dict[str, Any]] = {
    "HighFantasy": {
        "label": "ハイファンタジー",
        "aliases": [
            # G1
            "fan",
            # G3
            "fantasy",
            "modern_fantasy",
            "dark_fantasy",
            # G2
            "ハイファンタジー (R15)",
            "ダークファンタジー (R15)",
            # G4
            "ファンタジー",
            "ハイファンタジー",
            "ダークファンタジー",
            # 旧3表 / 旧11キーワード
            "異世界",
            "異世界転生",
            "テンセイ",
            "チート転生",
        ],
        "domain": "fantasy",
        "preset_key": "cheat_tensei",
        "rating": "r15",
    },
    "Scifi": {
        "label": "SF",
        "aliases": [
            # G1
            "sf",
            # G3
            "scifi",
            # G4
            "SF",
        ],
        "domain": "scifi",
        "preset_key": "cheat_tensei",
        "rating": "all",
    },
    "Romance": {
        "label": "恋愛",
        "aliases": [
            # G1 / G3
            "romance",
            # G4
            "恋愛",
        ],
        "domain": "romance",
        "preset_key": "aku_reijo",
        "rating": "all",
    },
    "EroticRomance": {
        "label": "官能/ロマンス",
        "aliases": [
            # G4
            "官能/ロマンス",
        ],
        "domain": "romance",
        "preset_key": "pure_love_erotic",
        "rating": "r18",
    },
    "Mystery": {
        "label": "ミステリー",
        "aliases": [
            # G1
            "mystery",
            "ミステリー",
        ],
        "domain": "mystery",
        "preset_key": "loop",
        "rating": "all",
    },
    "Horror": {
        "label": "ホラー",
        "aliases": [
            # G1
            "horror",
            "ホラー",
        ],
        "domain": "horror",
        "preset_key": "zarma",
        "rating": "r18",
    },
    "Modern": {
        "label": "現代",
        "aliases": [
            # G4
            "現代",
            # 旧3表のキーワード
            "現代チート",
            "modern_cheat",
        ],
        "domain": "modern",
        "preset_key": "modern_cheat",
        "rating": "all",
    },
    "History": {
        "label": "歴史",
        "aliases": [
            # G4
            "歴史",
            "history",
        ],
        "domain": "history",
        "preset_key": "slow_life",
        "rating": "all",
    },
    "Youth": {
        "label": "青春",
        "aliases": [
            "youth",
            "青春",
            "ライトノベル",
        ],
        "domain": "youth",
        "preset_key": "loop",
        "rating": "all",
    },
    "Other": {
        "label": "その他",
        "aliases": [
            # G1
            "other",
            # G4
            "その他",
        ],
        "domain": "other",
        "preset_key": "zarma",
        "rating": "all",
    },
    "Zarma": {
        "label": "追放ざまぁ",
        "aliases": [
            "zarma",
            "ざまぁ",
            "追放ざまぁ",
        ],
        "domain": "fantasy",
        "preset_key": "zarma",
        "rating": "r15",
    },
    "AkuReijo": {
        "label": "悪役令嬢・婚約破棄",
        "aliases": [
            "aku_reijo",
            "悪役令嬢",
            "悪役令嬢・婚約破棄",
        ],
        "domain": "romance",
        "preset_key": "aku_reijo",
        "rating": "r15",
    },
    "SlowLife": {
        "label": "スローライフ",
        "aliases": [
            "slow_life",
            "slowlife",
            "追放後スローライフ",
        ],
        "domain": "fantasy",
        "preset_key": "slow_life",
        "rating": "all",
    },
    "DungeonAdmin": {
        "label": "ダンジョン運営",
        "aliases": [
            "dungeon_admin",
            "ダンジョン運営",
        ],
        "domain": "fantasy",
        "preset_key": "dungeon_admin",
        "rating": "all",
    },
    "Vrmmo": {
        "label": "VRMMO・ゲーム世界",
        "aliases": [
            "vrmmo",
            "VRMMO・ゲーム世界",
        ],
        "domain": "fantasy",
        "preset_key": "vrmmo",
        "rating": "all",
    },
    "Loop": {
        "label": "ループ",
        "aliases": [
            "loop",
            "ループもの",
        ],
        "domain": "fantasy",
        "preset_key": "loop",
        "rating": "all",
    },
    "TsTensei": {
        "label": "TS転生",
        "aliases": [
            "ts_tensei",
            "TS転生",
        ],
        "domain": "fantasy",
        "preset_key": "ts_tensei",
        "rating": "r15",
    },
}


# 旧 easy_mode.GENRE_TO_PRESET の11キーワードを **評価順のまま** 保持する。
# 特に ("ざまぁ" -> zarma) が ("ループ" -> loop) より先に来る優先順位差は意味論なので維持する。
LEGACY_KEYWORD_PRIORITY: list[tuple[str, str]] = [
    ("ざまぁ", "zarma"),
    ("令嬢", "aku_reijo"),
    ("VRMMO", "vrmmo"),
    ("ダンジョン", "dungeon_admin"),
    ("スローライフ", "slow_life"),
    ("追放", "slow_life"),
    ("ループ", "loop"),
    ("テンセイ", "cheat_tensei"),
    ("現代チート", "modern_cheat"),
    ("異世界転生", "cheat_tensei"),
    ("ダークファンタジー", "cheat_tensei"),
]

# キーワード -> 解決先レジストリキー（上記と同じ評価順）
_KEYWORD_TO_ENTRY: dict[str, str] = {
    "ざまぁ": "Zarma",
    "令嬢": "AkuReijo",
    "VRMMO": "Vrmmo",
    "ダンジョン": "DungeonAdmin",
    "スローライフ": "SlowLife",
    "追放": "SlowLife",
    "ループ": "Loop",
    "テンセイ": "HighFantasy",
    "現代チート": "Modern",
    "異世界転生": "HighFantasy",
    "ダークファンタジー": "HighFantasy",
}

# 検索を高速化するための索引（alias -> entry key、大文字小文字を区別しない）
_ALIAS_INDEX: dict[str, str] = {}
for _key, _entry in GENRE_REGISTRY.items():
    _ALIAS_INDEX.setdefault(_key.casefold(), _key)
    _ALIAS_INDEX.setdefault(str(_entry["label"]).casefold(), _key)
    for _alias in _entry["aliases"]:
        _ALIAS_INDEX.setdefault(str(_alias).casefold(), _key)
del _key, _entry, _alias


def resolve_genre(value: str | None) -> dict[str, Any] | None:
    """旧4系統のいずれの値でも 1 つのレジストリエントリに解決する。

    解決順:
    1. 完全一致（レジストリキー / label / alias、大文字小文字無視）
    2. 旧11キーワードの部分一致（優先順位順）
    3. label の部分一致

    未知の値は **サイレントな既定代入をせず** None を返す。
    """
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None

    hit = _ALIAS_INDEX.get(v.casefold())
    if hit is not None:
        return GENRE_REGISTRY[hit]

    for keyword, _preset_key in LEGACY_KEYWORD_PRIORITY:
        if keyword in v:
            return GENRE_REGISTRY[_KEYWORD_TO_ENTRY[keyword]]

    folded = v.casefold()
    for entry in GENRE_REGISTRY.values():
        if str(entry["label"]).casefold() in folded:
            return entry
    return None


def resolve_preset_key(value: str | None) -> str | None:
    """値から preset key を解決する。未知の値は None。"""
    entry = resolve_genre(value)
    return str(entry["preset_key"]) if entry else None


def genre_payload() -> dict[str, dict[str, Any]]:
    """FE 配信用のレジストリ（中身はそのまま、内部インデックスは含めない）。"""
    return {
        key: {
            "key": key,
            "label": entry["label"],
            "domain": entry["domain"],
            "preset_key": entry["preset_key"],
            "rating": entry["rating"],
            "aliases": list(entry["aliases"]),
        }
        for key, entry in GENRE_REGISTRY.items()
    }
