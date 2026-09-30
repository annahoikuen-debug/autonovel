"""閉じたビート語彙の構造的整合性の回帰テスト。"""

import pytest

from config.story_spine.beat import ARTIFACTS, BEAT_VOCABULARY, ROLES


def test_vocabulary_is_not_empty():
    assert len(BEAT_VOCABULARY) >= 30, f"語彙が {len(BEAT_VOCABULARY)} 語しかない"


def test_keys_are_unique():
    """dict への変換で重複が黙って潰されていないこと。"""
    from config.story_spine.beat import BEAT_LIST

    assert len(BEAT_LIST) == len(BEAT_VOCABULARY), (
        f"beat key の重複がある: {len(BEAT_LIST)} 件 → {len(BEAT_VOCABULARY)} 件"
    )
    assert list(BEAT_VOCABULARY) == list(dict.fromkeys(BEAT_VOCABULARY))


def test_all_spans_are_relative():
    """**絶対話数が混入していないことの構造テスト**（本計画の最重要不変条件）。"""
    offenders = [
        f"{k}: {b.span}"
        for k, b in BEAT_VOCABULARY.items()
        if not (0.0 <= b.span[0] < b.span[1] <= 1.0)
    ]
    assert not offenders, f"相対でない span がある: {offenders}"


def test_roles_and_artifacts_are_from_closed_vocabulary():
    for k, b in BEAT_VOCABULARY.items():
        assert b.role in ROLES, f"{k}.role={b.role!r} が ROLES に無い"
        assert b.artifact in ARTIFACTS, f"{k}.artifact={b.artifact!r} が ARTIFACTS に無い"


def test_tension_in_unit_range():
    for k, b in BEAT_VOCABULARY.items():
        assert 0.0 <= b.tension <= 1.0, f"{k}.tension={b.tension}"


def test_duty_is_single_imperative_sentence():
    """duty はプロンプトに注入される。1文・命令形に限定する。"""
    for k, b in BEAT_VOCABULARY.items():
        assert b.duty.endswith("。"), f"{k}.duty が命令文で終わっていない: {b.duty!r}"
        assert len(b.duty) <= 60, f"{k}.duty が長すぎる（{len(b.duty)}字）: {b.duty!r}"


def test_beat_is_frozen():
    with pytest.raises(Exception):
        BEAT_VOCABULARY["climax"].tension = 0.0  # frozen=True なので例外


def test_key_must_equal_dict_key():
    """語彙の key と dict のキーが食い違っていないこと（プロンプト注入が壊れる）。"""
    offenders = [k for k, b in BEAT_VOCABULARY.items() if b.key != k]
    assert not offenders, f"key 不一致: {offenders}"


def test_critical_beats_exist():
    """構造の3不変条件が前提となるビートが必ず存在すること。"""
    for required in ("inciting", "midpoint_reversal", "climax"):
        assert required in BEAT_VOCABULARY, f"必須ビート {required!r} が無い"
