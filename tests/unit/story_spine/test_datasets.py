"""データセットの整合性。参照切れ・語彙漏れ・重複を検出する。"""

from config.story_spine.beat import BEAT_VOCABULARY
from config.story_spine.loader import CARDS, LENGTHS, MARKETS, PATTERNS

# config/data/archetypes.json:9-258 から移設した既存 31 パターン（キーの保存が回帰防止の要）
REQUIRED_EXISTING_31 = {
    "exile_rise", "peerless_reincarnation", "avenger_dark", "bottom_up_growth",
    "master_disciple", "secret_identity", "dungeon_conqueror", "guild_rebuilder",
    "summon_hero_betrayal", "tournament_champion", "slow_life", "gourmet_conqueror",
    "territory_management", "alchemy_workshop", "pet_tamer", "craftsman_legend",
    "modern_knowledge", "villainess_destruction_avoid", "contract_marriage",
    "doted_saint", "academy_cinderella", "love_comedy_density", "death_loop",
    "vr_streamer", "brain_battle", "detective_mystery", "army_rational",
    "shadow_organization", "onmyo_exorcism", "space_odyssey", "reincarnation_cheat",
}
REQUIRED_NEW_7 = {
    "court_intrigue", "professional_procedure", "sports_growth", "horror_dread",
    "healing_care", "ensemble_fracture", "transformation_isekai",
}
ENGINES = {"conflict", "comfort", "connection", "enigma"}
AXES = {"A", "B", "C", "D"}


def test_pattern_count_is_38():
    assert len(PATTERNS) == 38, f"パターン数が {len(PATTERNS)}（38 のはず）"


def test_existing_31_keys_are_preserved():
    missing = REQUIRED_EXISTING_31 - set(PATTERNS)
    assert not missing, f"既存キーの欠落: {sorted(missing)}"


def test_new_7_patterns_exist():
    missing = REQUIRED_NEW_7 - set(PATTERNS)
    assert not missing, f"新規7種の欠落: {sorted(missing)}"


def test_every_beat_key_exists_in_vocabulary():
    """パターンが語彙に無い beat を参照していないこと（プロンプト注入時に落ちる）。"""
    offenders = [
        f"{pk}.{b['key']}"
        for pk, pat in PATTERNS.items()
        for b in pat.get("beats", [])
        if b["key"] not in BEAT_VOCABULARY
    ]
    assert not offenders, f"語彙に無い beat 参照: {offenders}"


def test_every_pattern_spans_are_monotonic_and_relative():
    for pk, pat in PATTERNS.items():
        prev = -1.0
        for b in pat.get("beats", []):
            s, e = b["span"]
            assert 0.0 <= s < e <= 1.0, f"{pk}.{b['key']} の span が不正: {b['span']}"
            assert s >= prev, f"{pk}.{b['key']} が前の beat と重なっている"
            prev = s


def test_every_pattern_has_climax():
    for pk, pat in PATTERNS.items():
        keys = [b["key"] for b in pat.get("beats", [])]
        assert "climax" in keys, f"{pk} に climax beat が無い"


def test_engines_and_axes_are_from_closed_set():
    for pk, pat in PATTERNS.items():
        assert pat.get("engine") in ENGINES, f"{pk}.engine={pat.get('engine')!r}"
        assert pat.get("axis") in AXES, f"{pk}.axis={pat.get('axis')!r}"


def test_lengths_market_counts():
    assert len(LENGTHS) == 6, f"長さ階層の数が {len(LENGTHS)}（6 のはず）"
    assert len(MARKETS) == 4, f"媒体規格の数が {len(MARKETS)}（4 のはず）"
    assert len(CARDS) == 24, f"カードの数が {len(CARDS)}（24 のはず）"


def test_card_references_are_all_valid():
    offenders = []
    for ck, card in CARDS.items():
        for field_name, table in (("pattern", PATTERNS), ("length", LENGTHS), ("market", MARKETS)):
            if card.get(field_name) not in table:
                offenders.append(f"{ck}.{field_name}={card.get(field_name)!r}")
    assert not offenders, f"カードの参照切れ: {offenders}"


def test_cards_cover_short_and_mid_length():
    """短編・中編の層が1枚も無いと本計画の目的が達成されない。"""
    used = {c.get("length") for c in CARDS.values()}
    assert "short" in used, "短編カードが無い"
    assert {"novella", "single_volume", "web_volume", "long_serial"} <= used


def test_length_char_counts_match_manuscript_presets():
    """`frontend/src/constants/manuscript.ts:3-48` の実在値からの転記であること。"""
    assert LENGTHS["short"]["target_chars"] == 12000
    assert LENGTHS["single_volume"]["target_chars"] == 55000
    assert LENGTHS["web_volume"]["target_chars"] == 100000
    assert LENGTHS["web_volume"]["eps_range"] == [40, 40]


def test_length_hook_window_scales_with_length():
    """つかみの必須話数は長さに応じて変わる（短編1話 → Web3話 → シリーズ5話）。"""
    assert LENGTHS["short"]["hook_window_eps"] == 1
    assert LENGTHS["web_volume"]["hook_window_eps"] == 3
    assert LENGTHS["series"]["hook_window_eps"] == 5


def test_foreshadow_scopes_narrow_for_short():
    """短編は長期伏線を持たない。"""
    assert LENGTHS["short"]["foreshadow_scopes"] == ["short"]
    assert "long" in LENGTHS["long_serial"]["foreshadow_scopes"]
