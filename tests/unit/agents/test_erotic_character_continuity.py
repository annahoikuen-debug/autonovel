"""src/agents/erotic/continuity.py の単体テスト (ContinuityTracker 部分)."""

from __future__ import annotations

import pytest

from src.agents.erotic.continuity import (
    CharacterStateSnapshot,
    ContinuityReport,
    ContinuityTracker,
)


@pytest.fixture
def tracker(tmp_path):
    return ContinuityTracker(str(tmp_path / "char.db"))


def test_report_model():
    rep = ContinuityReport(
        is_consistent=False, issues=["a"], checked_dimensions=["x"], character_name="A", episode_num=1
    )
    assert rep.character_name == "A"


def test_character_snapshot_defaults():
    snap = CharacterStateSnapshot(character_name="A", episode_num=1)
    assert snap.custom_flags == {}
    assert snap.stamina_level == "normal"
    with pytest.raises(Exception):
        CharacterStateSnapshot(character_name="A", episode_num=1, bogus=1)


def test_save_and_get_snapshot_memory_and_db(tracker):
    snap = CharacterStateSnapshot(character_name="A", episode_num=1, stamina_level="tired", custom_flags={"x": "y"})
    tracker.save_snapshot(snap)
    got = tracker.get_snapshot(1, "A")
    assert got.stamina_level == "tired"
    assert got.custom_flags == {"x": "y"}

    # メモリキャッシュ cleared -> SQLite から復元
    fresh = ContinuityTracker(tracker.db_path)
    got2 = fresh.get_snapshot(1, "A")
    assert got2.stamina_level == "tired"
    assert got2.custom_flags == {"x": "y"}
    assert fresh.get_snapshot(9, "Z") is None
    assert fresh.get_previous_snapshot(2, "A") is not None


def test_save_snapshot_db_failure_is_logged(tracker, monkeypatch):
    import sqlite3

    real_connect = sqlite3.connect

    def boom(*a, **k):
        raise RuntimeError("no db")

    monkeypatch.setattr(sqlite3, "connect", boom)
    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=2))
    # メモリには保存されている
    assert tracker.get_snapshot(2, "A").character_name == "A"


def test_init_db_failure_is_logged(monkeypatch):
    import sqlite3

    def boom(*a, **k):
        raise RuntimeError("no db")

    monkeypatch.setattr(sqlite3, "connect", boom)
    t = ContinuityTracker("/nonexistent-dir/x.db")
    assert t._snapshots == {}


def test_get_snapshot_db_failure_returns_none(tracker, monkeypatch):
    import sqlite3

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert tracker.get_snapshot(5, "A") is None


def test_get_snapshot_invalid_json_flags(tracker):
    import contextlib
    import sqlite3

    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1))
    with contextlib.closing(sqlite3.connect(tracker.db_path)) as conn:
        conn.execute("UPDATE character_continuity_snapshots SET custom_flags = ? ", ("{bad json",))
        conn.commit()
    fresh = ContinuityTracker(tracker.db_path)
    assert fresh.get_snapshot(1, "A").custom_flags == {}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("疲弊し倒れ、限界で動けない", "exhausted"),
        ("疲れ、だるい、重い体", "tired"),
        ("元気、活力、力が漲る", "energetic"),
        ("普通の文章", "normal"),
    ],
)
def test_detect_stamina(text, expected):
    assert ContinuityTracker._detect_stamina(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("絶望と恐怖と崩壊", "distressed"),
        ("不安と怯えと緊張", "anxious"),
        ("安心と満足と穏やか", "content"),
        ("恍惚と歓喜と至福", "euphoric"),
        ("普通の文章", "neutral"),
    ],
)
def test_detect_psych_state(text, expected):
    assert ContinuityTracker._detect_psych_state(text) == expected


def test_detect_location():
    assert ContinuityTracker._detect_location("部屋と室内と寝室") == "indoor"
    assert ContinuityTracker._detect_location("森と庭と野原") == "outdoor"
    assert ContinuityTracker._detect_location("何でもない") == "unknown"


def test_detect_intimacy():
    assert ContinuityTracker._detect_intimacy("初対面") == "stranger"
    assert ContinuityTracker._detect_intimacy("信頼し心を開く") == "close"
    assert ContinuityTracker._detect_intimacy("肌を重ねる") == "intimate"
    assert ContinuityTracker._detect_intimacy("運命を誓い、魂が離れられぬ") == "bonded"
    assert ContinuityTracker._detect_intimacy("何でもない") == "acquaintance"


def test_detect_clothing_state(tracker):
    from src.agents.erotic.filter import EroticIntegrityChecker

    verbs = " ".join(EroticIntegrityChecker.UNDRESS_VERBS)
    dress = " ".join(EroticIntegrityChecker.DRESS_VERBS)
    one = EroticIntegrityChecker.UNDRESS_VERBS[0]
    assert tracker._detect_clothing_state(" ".join([one] * 4)) == "fully_undressed"
    assert tracker._detect_clothing_state(one) == "partially_undressed"
    assert tracker._detect_clothing_state(f"{verbs} {verbs} {verbs} {verbs}") == "fully_undressed"
    assert tracker._detect_clothing_state(f"{dress} {dress} {dress}") == "fully_dressed"


def test_extract_snapshot(tracker):
    long_text = "x" * 300 + "部屋の中で回復し、元気に弾む"
    snap = tracker.extract_snapshot("A", 1, long_text)
    assert snap.character_name == "A"
    assert snap.location == "indoor"
    explicit = tracker.extract_snapshot("A", 1, "text", clothing_state="fully_undressed")
    assert explicit.clothing_state == "fully_undressed"


def test_check_stamina_continuity(tracker):
    assert tracker.check_stamina_continuity(2, "A", "x") == []
    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, stamina_level="exhausted")
    )
    issues = tracker.check_stamina_continuity(2, "A", "元気と活力と力が漲る" * 20)
    assert any("体力矛盾" in i for i in issues)
    assert tracker.check_stamina_continuity(2, "A", "疲弊と限界で動けない" * 20) == []


def test_check_recovery_description(tracker):
    assert tracker.check_recovery_description(2, "A", "x") == []
    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1, stamina_level="tired"))
    assert any("回復描写不足" in i for i in tracker.check_recovery_description(2, "A", "何でもない" * 40))
    assert tracker.check_recovery_description(2, "A", "朝、目覚めて回復した" * 30) == []


@pytest.mark.parametrize(
    "level,num", [("exhausted", 0), ("tired", 1), ("normal", 2), ("energetic", 3), ("zzz", 2)]
)
def test_stamina_to_num(level, num):
    assert ContinuityTracker._stamina_to_num(level) == num


def test_check_stamina_jump(tracker):
    assert tracker.check_stamina_jump(2, "A", "x") == []
    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, stamina_level="exhausted")
    )
    assert any("体力急変" in i for i in tracker.check_stamina_jump(2, "A", "何でもない" * 40))


def test_check_psych_continuity(tracker):
    assert tracker.check_psych_continuity(2, "A", "x") == []
    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, psych_state="distressed")
    )
    assert any("心理矛盾" in i for i in tracker.check_psych_continuity(2, "A", "恍惚と歓喜と至福" * 20))
    assert tracker.check_psych_continuity(2, "A", "不安と怯えと緊張" * 20) == []


def test_check_psych_trigger(tracker):
    assert tracker.check_psych_trigger(2, "A", "x") == []
    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, psych_state="distressed")
    )
    assert any(
        "心理トリガー不足" in i
        for i in tracker.check_psych_trigger(2, "A", "安心と満足と穏やか" * 20)
    )
    assert tracker.check_psych_trigger(2, "A", "受け入れられ、許されて救われた" * 20) == []

    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, psych_state="euphoric")
    )
    assert any(
        "心理トリガー不足" in i
        for i in tracker.check_psych_trigger(2, "A", "絶望と恐怖と崩壊" * 20)
    )
    assert tracker.check_psych_trigger(2, "A", "別れを告げ、失った" * 20) == []


@pytest.mark.parametrize(
    "state,num", [("distressed", 0), ("anxious", 1), ("neutral", 2), ("content", 3), ("euphoric", 4), ("?", 2)]
)
def test_psych_to_num(state, num):
    assert ContinuityTracker._psych_to_num(state) == num


def test_check_psych_jump(tracker):
    assert tracker.check_psych_jump(2, "A", "x") == []
    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, psych_state="distressed")
    )
    assert any("心理急変" in i for i in tracker.check_psych_jump(2, "A", "恍惚と歓喜と至福" * 20))


def test_has_time_passage(tracker):
    assert tracker._has_time_passage("翌朝、目が覚めた") is True
    assert tracker._has_time_passage("何でもない") is False


def test_check_clothing_continuity(tracker):
    assert tracker.check_clothing_continuity(2, "A", "x") == []
    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, clothing_state="fully_undressed")
    )
    assert any("衣服引き継ぎ矛盾" in i for i in tracker.check_clothing_continuity(2, "A", "彼は歩いた"))
    assert tracker.check_clothing_continuity(2, "A", "翌朝彼は歩いた") == []


def test_check_clothing_continuity_dressed_verbs(tracker):
    from src.agents.erotic.filter import EroticIntegrityChecker

    tracker.save_snapshot(
        CharacterStateSnapshot(character_name="A", episode_num=1, clothing_state="partially_undressed")
    )
    text = EroticIntegrityChecker.DRESS_VERBS[0]
    assert tracker.check_clothing_continuity(2, "A", f"彼は{text}した") == []
    kw = EroticIntegrityChecker.DRESS_KEYWORDS[0]
    assert tracker.check_clothing_continuity(2, "A", f"彼は{kw}を着た") == []


@pytest.mark.parametrize(
    "level,num", [("stranger", 0), ("acquaintance", 1), ("close", 2), ("intimate", 3), ("bonded", 4), ("x", 1)]
)
def test_intimacy_to_num(level, num):
    assert ContinuityTracker._intimacy_to_num(level) == num


def test_check_intimacy_regression_and_rush(tracker):
    assert tracker.check_intimacy_regression(2, "A", "x") == []
    assert tracker.check_intimacy_rush(2, "A", "x") == []
    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1, intimacy_level="bonded"))
    assert any("親密度後退" in i for i in tracker.check_intimacy_regression(2, "A", "初対面の見知らぬ人"))
    assert tracker.check_intimacy_rush(2, "A", "何でもない") == []

    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1, intimacy_level="stranger"))
    assert any("親密度急進" in i for i in tracker.check_intimacy_rush(2, "A", "運命を誓い、魂が離れられぬ"))
    assert tracker.check_intimacy_regression(2, "A", "何でもない") == []


def test_check_intimacy_vs_erotic_level(tracker):
    assert tracker.check_intimacy_vs_erotic_level(2, "A", "x") == []
    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1, intimacy_level="stranger"))
    assert any("親密度不足" in i for i in tracker.check_intimacy_vs_erotic_level(2, "A", "肌を重ねた"))
    assert tracker.check_intimacy_vs_erotic_level(2, "A", "何でもない") == []
    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1, intimacy_level="close"))
    assert tracker.check_intimacy_vs_erotic_level(2, "A", "肌を重ねた") == []


def test_check_location_continuity(tracker):
    assert tracker.check_location_continuity(2, "A", "x") == []
    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1, location="unknown"))
    assert tracker.check_location_continuity(2, "A", "森と庭と野原") == []
    tracker.save_snapshot(CharacterStateSnapshot(character_name="A", episode_num=1, location="indoor"))
    assert any("場所矛盾" in i for i in tracker.check_location_continuity(2, "A", "森と庭と野原"))
    assert tracker.check_location_continuity(2, "A", "森に移動した") == []
    assert tracker.check_location_continuity(2, "A", "翌朝、森と庭と野原") == []
    assert tracker.check_location_continuity(2, "A", "何でもない") == []


def test_check_environment_consistency(tracker):
    assert tracker.check_environment_consistency("雪が降る", "霧が深い") == []
    assert any(
        "環境矛盾" in i for i in tracker.check_environment_consistency("雨が降っていた", "空は晴れていた")
    )
    assert tracker.check_environment_consistency("雨が降っていた", "翌朝、晴れていた") == []
    assert tracker.check_environment_consistency("雪", "晴れ") != []
    assert tracker.check_environment_consistency("嵐", "晴れ") != []
