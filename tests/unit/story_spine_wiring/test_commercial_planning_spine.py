"""商業構成が Spine 単一ソースに統一されたことの確認。"""

from pathlib import Path


def test_four_act_hardcode_removed():
    """4幕ハードコードが復活していないこと。"""
    src = Path("src/backend/routers/commercial_planning.py").read_text(encoding="utf-8")
    assert '["起 (Setup)"' not in src, "4幕のハードコードが復活している"
    assert "min(3, (ep - 1) * 4" not in src, "4幕のインデックス計算が復活している"


def test_beat_sheet_request_has_spine_defaults():
    """既定値が既存呼び出しを壊さないこと。"""
    from src.backend.routers.commercial_planning import BeatSheetGenerateRequest

    req = BeatSheetGenerateRequest(title="t", synopsis="")
    assert req.pattern_key == "exile_rise"
    assert req.length_key == "web_volume"
    assert req.market_key == "web"
    assert req.target_episodes == 40


def test_beat_sheet_request_accepts_custom_pattern():
    from src.backend.routers.commercial_planning import BeatSheetGenerateRequest

    req = BeatSheetGenerateRequest(title="t", synopsis="", pattern_key="healing_care", target_episodes=5)
    assert req.pattern_key == "healing_care"


def test_commercial_beat_sheet_still_present():
    """**既存利用者を壊していないことの確認**。`src/agents/planning.py` が使っている。"""
    from src.config.commercial_beat_sheet import COMMERCIAL_40EP_BEATS

    assert len(COMMERCIAL_40EP_BEATS) == 7


def test_agent_planning_still_imports():
    """`src/agents/planning.py` の COMMERCIAL_40EP_BEATS 参照が生きていること。"""
    import src.agents.planning as planning

    src = Path(planning.__file__).read_text(encoding="utf-8")
    assert "COMMERCIAL_40EP_BEATS" in src, "planning.py が COMMERCIAL_40EP_BEATS を使わなくなった"


def test_spine_replaces_the_four_act_curve():
    """4幕のテンション式が消え、Spine を使う形的になっていること。"""
    src = Path("src/backend/routers/commercial_planning.py").read_text(encoding="utf-8")
    assert "resolve_spine" in src
    assert "progress < 0.25" not in src, "4幕ベースのテンション式が残っている"


def test_five_act_beat_sheet_works():
    """5話の構成でも各話に beat が割り当てられること。"""
    from src.services.spine_resolver import resolve_spine

    spine = resolve_spine("healing_care", "short", "general", 5)
    assert [spine.at(ep) is not None for ep in range(1, 6)] == [True] * 5
