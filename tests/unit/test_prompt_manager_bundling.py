"""背景伏線の選択・省略サマリの回帰テスト（PLAN_W5 Step 11 / W5-10）。"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from prompts.manager import PromptManager  # noqa: E402


def _fs(i: int, planted: int, target: int) -> dict:
    return {
        "id": i,
        "title": f"伏線{i}",
        "description": "d",
        "planted_episode": planted,
        "target_episode": target,
    }


def test_overdue_still_ranks_first():
    rows = [_fs(1, 1, 3), _fs(2, 2, 2), _fs(3, 3, 30)]
    shown, _ = PromptManager._select_background_foreshadowings(rows, [], current_episode=10)
    assert shown[0]["id"] == 2


def test_cap_is_still_twenty():
    rows = [_fs(i, i, 100) for i in range(1, 51)]
    shown, note = PromptManager._select_background_foreshadowings(rows, [], current_episode=5)
    assert len(shown) == 20
    assert "他30件" in note


def test_note_mentions_recommended_episodes():
    rows = [_fs(i, i, 10 + i) for i in range(1, 6)]
    shown, note = PromptManager._select_background_foreshadowings(rows, [], current_episode=5)
    assert "回収推奨" in note
    assert "第11話" in note


def test_contract_items_are_excluded_from_background():
    contract = [{"id": 99, "title": "契約", "planted_episode": 1, "target_episode": 5}]
    shown, _ = PromptManager._select_background_foreshadowings(
        [_fs(99, 1, 5), _fs(1, 2, 6)], contract, current_episode=5
    )
    assert all(f["id"] != 99 for f in shown)


def test_empty_input_is_safe():
    shown, note = PromptManager._select_background_foreshadowings([], [], current_episode=1)
    assert shown == []
    assert note == ""


def test_nearest_payoff_ranks_before_farther_one():
    """回収予定が今話に近いものを先に並べる（終端一斉押し寄せの緩和）。"""
    rows = [_fs(1, 1, 38), _fs(2, 2, 12), _fs(3, 3, 20)]
    shown, _ = PromptManager._select_background_foreshadowings(rows, [], current_episode=10)
    assert [f["id"] for f in shown] == [2, 3, 1]


def test_bundle_limit_is_five():
    assert PromptManager.FORESHADOW_BUNDLE_LIMIT == 5
    rows = [_fs(i, i, 20 + i) for i in range(1, 11)]
    _, note = PromptManager._select_background_foreshadowings(rows, [], current_episode=10)
    # 回収推奨は上限 5 件まで
    assert note.count("第") == 5


def test_cap_constant_is_unchanged():
    assert PromptManager.MAX_BACKGROUND_FORESHADOWINGS == 20


def test_overdue_episodes_are_excluded_from_recommendation():
    """期限超過话は「回収推奨」（= 今後の話）に混ぜない。"""
    rows = [_fs(1, 1, 3), _fs(2, 2, 8), _fs(3, 3, 15)]
    _, note = PromptManager._select_background_foreshadowings(rows, [], current_episode=10)
    assert "第15話" in note
    assert "第8話" not in note
    assert "第3話" not in note
