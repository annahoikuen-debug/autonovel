"""src/agents/erotic/continuity.py の単体テスト (SceneContinuityTracker 部分)."""

from __future__ import annotations

import pytest

from src.agents.erotic.continuity import SceneContinuityTracker, SceneStateSnapshot


@pytest.fixture
def tracker(tmp_path):
    return SceneContinuityTracker(str(tmp_path / "scene.db"))


def test_snapshot_defaults_and_extra_forbid():
    snap = SceneStateSnapshot()
    assert snap.discoveries == []
    assert snap.items_held == []
    assert snap.injury_level == "none"
    with pytest.raises(Exception):
        SceneStateSnapshot(unknown_field=1)


def test_to_illustration_prompt_minimal():
    snap = SceneStateSnapshot()
    assert snap.to_illustration_prompt() == "masterpiece, best quality, highly detailed anime illustration"


def test_to_illustration_prompt_hostile_with_injury():
    snap = SceneStateSnapshot(
        character_name="Alice",
        scene_type="combat",
        time_of_day="night",
        attitude="hostile",
        injury_level="light",
        discoveries=["a"],
        items_held=["sword"],
    )
    prompt = snap.to_illustration_prompt(["extra"])
    assert "1girl, Alice" in prompt
    assert "combat scene" in prompt
    assert "night" in prompt
    assert "glaring, tense atmosphere" in prompt
    assert "scratches, torn clothes" in prompt
    assert "extra" in prompt


@pytest.mark.parametrize(
    "attitude,expected",
    [
        ("friendly", "gentle smile, warm lighting"),
        ("sensual", "blushing, heavy breathing, parted lips, soft romantic lighting"),
        ("intimate", "blushing, heavy breathing, parted lips, soft romantic lighting"),
        ("neutral", None),
    ],
)
def test_to_illustration_prompt_attitudes(attitude, expected):
    snap = SceneStateSnapshot(attitude=attitude)
    prompt = snap.to_illustration_prompt()
    if expected:
        assert expected in prompt
    else:
        assert "lighting" not in prompt


def test_save_and_get_snapshot(tracker):
    snap = SceneStateSnapshot(
        character_name="A",
        episode_num=1,
        injury_level="light",
        attitude="hostile",
        discoveries=["x"],
        travel_state="departing",
        recovery_state="action",
        perspective="third_person",
        foreshadowing_active=True,
        time_of_day="night",
        items_held=["key"],
    )
    tracker.save_snapshot(snap)
    got = tracker.get_snapshot(1, "A")
    assert got is not None
    assert got.injury_level == "light"
    assert got.discoveries == ["x"]
    assert got.items_held == ["key"]
    assert got.foreshadowing_active is True
    assert tracker.get_snapshot(9, "Nobody") is None
    # 上書き (INSERT OR REPLACE)
    snap.injury_level = "severe"
    tracker.save_snapshot(snap)
    assert tracker.get_snapshot(1, "A").injury_level == "severe"


def test_get_previous_snapshot(tracker):
    assert tracker.get_previous_snapshot(1, "A") is None
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, time_of_day="day"))
    assert tracker.get_previous_snapshot(2, "A").time_of_day == "day"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("彼は瀕死だった", "severe"),
        ("深手を用いた", "moderate"),
        ("かすり傷を負った", "light"),
        ("何もない", "none"),
    ],
)
def test_detect_injury_level(tracker, text, expected):
    assert tracker._detect_injury_level(text) == expected


def test_detect_attitude(tracker):
    assert tracker._detect_attitude("彼は拒絶し、罵倒した") == "hostile"
    assert tracker._detect_attitude("彼女はにこやかに微笑んだ") == "friendly"
    assert tracker._detect_attitude("沈黙が流れた") == "tense"
    assert tracker._detect_attitude("何でもない") == "neutral"


def test_detect_discoveries(tracker):
    text = "隠し部屋を発見した。raneは何もない。注意深い"
    assert tracker._detect_discoveries(text) == ["隠し部屋を発見した"]


def test_detect_travel_state(tracker):
    assert tracker._detect_travel_state("彼は旅立ち去った") == "departing"
    assert tracker._detect_travel_state(" 目的地に辿り着いた") == "arriving"
    assert tracker._detect_travel_state("ただ立っている") == "staying"


def test_detect_perspectives(tracker):
    assert tracker._detect_perspective("私は歩いた") == "first_person"
    assert tracker._detect_perspective("彼は歩いた") == "third_person"
    assert tracker._detect_monologue_perspective("俺は眠い") == "first_person"
    assert tracker._detect_monologue_perspective("誰もいない") == "third_person"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("彼はベッドで眠った", "resting"),
        ("傷が癒えてきた", "recovering"),
        ("激闘があった", "action"),
        ("彼は攻撃した", "action"),
        ("何もない", "unknown"),
    ],
)
def test_detect_recovery_state(tracker, text, expected):
    assert tracker._detect_recovery_state(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("朝の街", "morning"),
        ("正午の太陽", "day"),
        ("夕暮れの街", "evening"),
        ("深夜の月明かり", "night"),
        ("何もない", "unknown"),
    ],
)
def test_detect_time_of_day(tracker, text, expected):
    assert tracker._detect_time_of_day(text) == expected


def test_detect_item_ownership(tracker):
    found = tracker._detect_item_ownership("彼は聖剣と鎧と剣を持ち、巻物を手に入れた")
    assert "聖剣" in found
    assert "鎧" in found
    # 長い語が先
    assert found.index("聖剣") < found.index("剣") if "剣" in found else True
    assert tracker._detect_item_ownership("何もない") == []


def test_detect_foreshadowing(tracker):
    assert tracker._detect_foreshadowing("何もない") == []
    assert len(tracker._detect_foreshadowing("予感がある")) >= 1


def test_extract_snapshot(tracker):
    snap = tracker.extract_snapshot("彼女は微笑んだ。隠された扉を発見した。")
    assert snap.attitude in ("friendly", "neutral")
    assert snap.discoveries


# ---------------------------------------------------------------- continuity


def test_checks_return_empty_without_previous(tracker):
    for fn in (
        tracker.check_injury_continuity,
        tracker.check_attitude_continuity,
        tracker.check_discovery_continuity,
        tracker.check_travel_continuity,
        tracker.check_recovery_continuity,
        tracker.check_perspective_continuity,
        tracker.check_foreshadowing_continuity,
        tracker.check_time_continuity,
        tracker.check_item_continuity,
    ):
        assert fn(1, "A", "テキスト") == []


def test_check_injury_unnatural_recovery(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, injury_level="severe"))
    issues = tracker.check_injury_continuity(2, "A", "彼は普通に歩いていた")
    assert any("不自然に回復" in i for i in issues)


def test_check_injury_recovery_with_treatment(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, injury_level="severe"))
    issues = tracker.check_injury_continuity(2, "A", "治療を受け、回復した")
    assert not any("不自然に回復" in i for i in issues)


def test_check_injury_sudden_worsening(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, injury_level="light"))
    issues = tracker.check_injury_continuity(2, "A", "瀕死の深手を負った")
    assert any("【状態急変】" in i for i in issues)


def test_check_attitude_continuity(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, attitude="hostile"))
    issues = tracker.check_attitude_continuity(2, "A", "彼はにこやかに微笑んだ")
    assert any("態度が不自然に変化" in i for i in issues)
    # 中立 -> 何もしない
    assert tracker.check_attitude_continuity(2, "A", "何でもない") == []


def test_check_discovery_continuity(tracker):
    tracker.save_snapshot(
        SceneStateSnapshot(character_name="A", episode_num=1, discoveries=["王の秘密"])
    )
    issues = tracker.check_discovery_continuity(2, "A", "彼は眠った")
    assert any("重要な情報" in i for i in issues)
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, discoveries=["何もない話"]))
    assert tracker.check_discovery_continuity(2, "A", "彼は眠った") == []


def test_check_travel_continuity_both_directions(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, travel_state="departing"))
    assert any("移動断絶" in i for i in tracker.check_travel_continuity(2, "A", "彼は立っていた"))
    assert tracker.check_travel_continuity(2, "A", "目的地に到着した") == []

    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, travel_state="arriving"))
    assert any("移動断絶" in i for i in tracker.check_travel_continuity(2, "A", "彼は出発した"))
    assert tracker.check_travel_continuity(2, "A", "宿で滞在した") == []


def test_check_perspective_continuity(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, perspective="first_person"))
    issues = tracker.check_perspective_continuity(2, "A", "彼は歩いた")
    assert any("視点警告" in i for i in issues)
    assert tracker.check_perspective_continuity(2, "A", "私は歩いた") == []


def test_check_recovery_continuity(tracker):
    tracker.save_snapshot(
        SceneStateSnapshot(character_name="A", episode_num=1, recovery_state="action", injury_level="severe")
    )
    assert any("治療描写なしに回復" in i for i in tracker.check_recovery_continuity(2, "A", "体力が戻ってきた"))
    assert any("連戦警告" in i for i in tracker.check_recovery_continuity(2, "A", "激闘を続けた"))
    # 治療描写があっても「連戦警告」は残る（分岐ロジック通り）
    assert any("連戦警告" in i for i in tracker.check_recovery_continuity(2, "A", "治療を受けた。激闘を続けた"))

    tracker.save_snapshot(
        SceneStateSnapshot(character_name="A", episode_num=1, recovery_state="resting", injury_level="none")
    )
    assert any("回復描写がないまま" in i for i in tracker.check_recovery_continuity(2, "A", "激闘があった"))
    assert tracker.check_recovery_continuity(2, "A", "回復して激闘があった") == []


def test_check_foreshadowing_continuity(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, foreshadowing_active=True))
    assert any("伏線警告" in i for i in tracker.check_foreshadowing_continuity(2, "A", "何もない"))
    assert tracker.check_foreshadowing_continuity(2, "A", "真名が判明した") == []
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, foreshadowing_active=False))
    assert tracker.check_foreshadowing_continuity(2, "A", "何もない") == []


def test_check_item_continuity(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, items_held=["聖剣"]))
    assert any("消失" in i for i in tracker.check_item_continuity(2, "A", "彼は歩いた"))
    assert tracker.check_item_continuity(2, "A", "聖剣を失った") == []
    assert tracker.check_item_continuity(2, "A", "聖剣を使った") is not None


def test_check_time_continuity(tracker):
    tracker.save_snapshot(SceneStateSnapshot(character_name="A", episode_num=1, time_of_day="morning"))
    assert tracker.check_time_continuity(2, "A", "昼沙滩だった") == []
    assert any("不自然に遷移" in i for i in tracker.check_time_continuity(2, "A", "夜更けだった"))
    assert tracker.check_time_continuity(2, "A", "翌朝、昼になった") == []
    assert tracker.check_time_continuity(2, "A", "何もない") == []


def test_check_all_continuity(tracker):
    tracker.save_snapshot(
        SceneStateSnapshot(
            character_name="A",
            episode_num=1,
            injury_level="severe",
            attitude="hostile",
            discoveries=["王の秘密"],
            travel_state="departing",
            recovery_state="resting",
            perspective="first_person",
            foreshadowing_active=True,
            time_of_day="morning",
            items_held=["聖剣"],
        )
    )
    issues = tracker.check_all_continuity(2, "A", "夜更け彼は歩いた")
    assert len(issues) > 3


def test_init_db_creates_table(tmp_path):
    import sqlite3

    path = str(tmp_path / "s.db")
    SceneContinuityTracker(path)
    with sqlite3.connect(path) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "scene_snapshots" in names
