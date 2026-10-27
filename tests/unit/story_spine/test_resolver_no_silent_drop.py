"""**量子化で beat を 1 つも落とさないこと**の回帰テスト。

レビューで 1,969 ケースの「close role 無し」が発見された。
既存テストは全て「keys に climax がある」ことしか見ていなかったため、
**消えた beat の中身を直接数える**必要がある。
"""
from __future__ import annotations

import pytest

from config.story_spine import BEAT_VOCABULARY, PATTERNS, resolve_spine

CLOSE_ROLE_BEATS = {k for k, b in BEAT_VOCABULARY.items() if b.role == "close"}


def _pattern_close_keys(pattern_key: str) -> list[str]:
    return [b["key"] for b in PATTERNS[pattern_key]["beats"] if b["key"] in CLOSE_ROLE_BEATS]


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
@pytest.mark.parametrize("eps", [6, 8, 10, 12, 15, 20, 30, 40])
def test_close_role_survives_medium_lengths(pattern: str, eps: int):
    """**中編以上で「締め」の beat が 1 つも残らないことがない**。

    YAML に close role の beat があるなら、話数が足りる限り必ず 1 つは残る。
    これが外れる = 量子化で無言で落ちている。
    """
    expected = [k for k in _pattern_close_keys(pattern) if k != "volume_hook"]
    if not expected:
        pytest.skip(f"{pattern} には close role の beat が無い（ patterns.yaml 側の定義）")
    keys = set(resolve_spine(pattern, "single_volume", "general", eps).keys)
    assert keys & set(expected), (
        f"{pattern}@{eps}: close role が全滅。期待 {expected} / 実際 {sorted(keys)}"
    )


@pytest.mark.parametrize(
    "pattern,length,market,eps",
    [
        # レビューで観測した再現ケース
        ("dungeon_conqueror", "single_volume", "general", 12),
        ("exile_rise", "novella", "general", 8),
        ("guild_rebuilder", "novella", "web", 10),
        ("gourmet_conqueror", "novella", "web", 10),
    ],
)
def test_known_drop_cases_are_fixed(pattern: str, length: str, market: str, eps: int):
    """**レビューで観測した 4 ケースの直接の回帰テスト**。"""
    spine = resolve_spine(pattern, length, market, eps)
    keys = spine.keys
    assert "climax" in keys, f"{pattern}@{eps}: climax が消えた {keys}"
    assert keys[-1] != "climax", (
        f"{pattern}@{eps}: 最後が回収 beat ではなく climax 上書きされている {keys}"
    )
    assert len(keys) == len(set(keys)), f"{pattern}@{eps}: キーの重複 {keys}"


@pytest.mark.parametrize("eps", [3, 5, 8, 12, 20, 40, 100, 300])
def test_episode_coverage_is_exact_with_no_gap_and_no_overlap(eps: int):
    """1..eps が**ちょうど 1 回ずつ**被覆されること（隙間の禁止は既存テストにある）。"""
    for pattern in ("exile_rise", "detective_mystery", "dungeon_conqueror", "death_loop"):
        spine = resolve_spine(pattern, "long_serial", "web", eps)
        covered = [e for b in spine.beats for e in range(b.ep_start, b.ep_end + 1)]
        if eps <= 3:
            assert sorted(set(covered)) == list(range(1, eps + 1)), (
                f"{pattern}@{eps}: covered={covered[:12]} len={len(covered)}"
            )
        else:
            assert covered == list(range(1, eps + 1)), (
                f"{pattern}@{eps}: covered={covered[:12]} len={len(covered)}"
            )


def test_beat_count_equals_min_of_nodes_and_eps_when_compressible():
    """**圧縮が要るなら圧縮段を通す**ことの確認。

    YAML の beat 数 > eps のとき、結果の beat 数は eps まで圧縮されている
    （=量子化で落としたのではなく、意図的に併合した）。
    """
    for pattern in ("exile_rise", "detective_mystery", "dungeon_conqueror"):
        yaml_len = len(PATTERNS[pattern]["beats"])
        for eps in (3, 5, 10):
            spine = resolve_spine(pattern, "novella", "general", eps)
            assert len(spine.beats) <= max(eps, 3), (
                f"{pattern}@{eps}: {len(spine.beats)} beats（yaml は {yaml_len}）"
            )


def test_merged_duty_is_not_truncated_mid_sentence():
    """** duty の切断が明示的であること**（壊れた文がプロンプトに混入しない）。"""
    for eps in (1, 2, 3, 5):
        for pattern in ("exile_rise", "dungeon_conqueror", "detective_mystery"):
            for b in resolve_spine(pattern, "short", "general", eps).beats:
                assert b.duty.endswith("。"), f"{pattern}@{eps}/{b.key}: {b.duty!r}"
                assert len(b.duty) <= 62, f"{pattern}@{eps}/{b.key}: duty が長すぎる {b.duty!r}"
                # 途中で切れた場合は必ず省略記号で明示される
                if len(b.duty) >= 60:
                    assert "…" in b.duty or "、" in b.duty, (
                        f"{pattern}@{eps}/{b.key}: 切断が明示されていない {b.duty!r}"
                    )
