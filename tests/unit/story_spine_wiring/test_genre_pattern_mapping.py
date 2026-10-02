"""**ジャンル → パターンの解決が死んでいないこと**の回帰テスト。

レビューで `g_entry.get("pattern")` が常に None（=常に exile_rise）が判明した。
"""
from __future__ import annotations

from config.story_spine import PATTERNS
from config.story_spine.genre_registry import GENRE_REGISTRY
from src.backend.routers.easy_mode import resolve_pattern_key


def test_every_genre_entry_declares_a_known_pattern():
    """全エントリに `patterns.yaml` に実在する pattern があること。"""
    missing, unknown = [], []
    for key, entry in GENRE_REGISTRY.items():
        p = entry.get("pattern")
        if not p:
            missing.append(key)
        elif p not in PATTERNS:
            unknown.append((key, p))
    assert not missing, f"pattern 未定義のジャンル: {missing}"
    assert not unknown, f"patterns.yaml に無い pattern: {unknown}"


def test_genres_do_not_all_collapse_to_one_pattern():
    """**全てが exile_rise に潰れていないこと**（元バグの直接の検出）。"""
    pats = {e.get("pattern") for e in GENRE_REGISTRY.values()}
    assert len(pats) >= 3, f"パターンが {len(pats)} 種類しかない（=解決が死んでいる）: {pats}"


def test_resolve_pattern_key_returns_distinct_values_for_distinct_genres():
    a = resolve_pattern_key("ミステリー")
    b = resolve_pattern_key("ホラー")
    c = resolve_pattern_key("ZFantasy")
    assert a != b, f"ミステリーとホラーが同じパターン {a} になった"


def test_resolve_pattern_key_never_raises_for_unknown_genre():
    for genre in ("", "存在しないジャンル", "ZZZ", None, 123):
        got = resolve_pattern_key(genre)
        assert got in PATTERNS, f"{genre!r} -> {got!r}"


def test_explicit_pattern_overrides_genre():
    assert resolve_pattern_key("ミステリー", explicit="death_loop") == "death_loop"
