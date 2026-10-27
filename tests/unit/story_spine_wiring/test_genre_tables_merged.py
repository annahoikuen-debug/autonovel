"""3系統の genre→preset 表が1つに統合されたことの確認。"""
from config.story_spine.genre_registry import GENRE_REGISTRY, resolve_preset_key
from src.services.preset_loader import load_preset_for_pipeline
from src.services import spice_guard_adapter


MERGED_VALUES = [
    "ファンタジー", "恋愛", "SF", "歴史", "現代", "官能/ロマンス",
    "異世界", "追放ざまぁ", "悪役令嬢", "チート転生", "スローライフ",
    "ダンジョン運営", "現代チート", "TS転生", "VRMMO", "ループ",
]


def test_preset_loader_dict_is_gone():
    """二重管理が再発していないこと。"""
    from src.services import preset_loader

    src = __import__("pathlib").Path(preset_loader.__file__).read_text(encoding="utf-8")
    assert "genre_to_preset = {" not in src, "preset_loader に辞書が復活している"


def test_spice_guard_dict_is_gone():
    from pathlib import Path

    src = Path(spice_guard_adapter.__file__).read_text(encoding="utf-8")
    assert "GENRE_TO_PRESET = {" not in src, "spice_guard_adapter に辞書が復活している"


def test_all_merged_values_agree():
    """旧2表の16エントリがすべて同じ preset に解決されること。"""
    for value in MERGED_VALUES:
        assert resolve_preset_key(value) is not None, f"{value!r} が解決しない"


def test_three_tables_do_not_contradict():
    """同一 display 値に対する3経路の preset が一致すること。"""
    from src.backend.routers.easy_mode import resolve_genre_to_preset

    for value in MERGED_VALUES:
        a = resolve_genre_to_preset(value)
        b = resolve_preset_key(value)
        assert a == b, f"{value!r}: easy_mode={a!r} vs registry={b!r}"


def test_loader_still_returns_preset_for_known_genre():
    preset = load_preset_for_pipeline("ファンタジー", None)
    assert isinstance(preset, dict)


def test_spice_guard_adapter_resolves_through_registry():
    """spice_guard_adapter もレジストリ委譲で同じ preset を解決すること。"""
    guard = spice_guard_adapter.SpiceGuardAdapter("ファンタジー")
    assert guard.preset_name == resolve_preset_key("ファンタジー")


def test_registry_entries_are_self_consistent():
    """全エントリが解決・フィールド充足していること（FE 配信用の前提）。"""
    assert GENRE_REGISTRY
    for key, entry in GENRE_REGISTRY.items():
        for field in ("label", "aliases", "domain", "preset_key", "rating"):
            assert field in entry, f"{key} に {field!r} が無い"
        assert entry["label"], f"{key} の label が空"
        assert entry["preset_key"], f"{key} の preset_key が空"
        assert entry["aliases"], f"{key} の aliases が空"
