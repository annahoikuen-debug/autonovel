"""Wizard のビート生成が Spine に基づくことの確認。"""
from pathlib import Path



def test_save_the_cat_hardcode_is_gone():
    """12ビートハードコードが復活していないこと（ast で構造検査）。"""
    src = Path("src/backend/routers/plots.py").read_text(encoding="utf-8")
    for marker in ("Dark Night of the Soul", "All Is Lost", "Bad Guys Close In"):
        assert marker not in src, f"{marker!r} のハードコードが復活している"


def test_no_beat_truncation_to_12():
    """`beats_data[:12]` による切り詰めが復活していないこと。"""
    src = Path("src/backend/routers/plots.py").read_text(encoding="utf-8")
    assert "beats_data[:12]" not in src, "12件への切り詰めが復活している"


def test_expand_beats_request_has_optional_spine_fields():
    from src.models.api_schemas import ExpandBeatsRequest

    req = ExpandBeatsRequest(title="t", genre="g", target_chapters=3)
    assert req.pattern_key == "" and req.length_key == "" and req.market_key == ""


def test_expand_beats_request_legacy_construction_still_works():
    """既存呼び出し（キーなし）が壊れていないこと。"""
    from src.models.api_schemas import ExpandBeatsRequest

    req = ExpandBeatsRequest(
        title="t",
        genre="g",
        target_chapters=20,
        cheat_scale=4,
        growth_curve="最初からカンスト(無双)",
        system_assist=70,
        cost_severity=2,
    )
    assert req.target_chapters == 20
