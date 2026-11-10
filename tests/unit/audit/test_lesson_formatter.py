"""H8: `PromptComposer._format_audit_lessons` の単体テスト。

fail-open（None/空/不正 → 空文字）、件数・文字数上限、フォーマットを検証。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from src.agents.prompt_composer import PromptComposer


class _DummyAgent:
    logger = None


def _composer() -> PromptComposer:
    return PromptComposer(agent=_DummyAgent())


def test_none_returns_empty():
    assert _composer()._format_audit_lessons(None) == ""


def test_empty_list_returns_empty():
    assert _composer()._format_audit_lessons([]) == ""


def test_not_iterable_returns_empty():
    assert _composer()._format_audit_lessons("not-a-list") == ""


def test_single_lesson_formatted():
    comp = _composer()
    out = comp._format_audit_lessons(
        [
            {
                "dimension": "deai",
                "lesson_text": "AI定型表現を使わない",
                "severity": "medium",
                "occurrences": 2,
                "last_seen_episode": 3,
            }
        ],
        max_items=5,
        block_max_chars=800,
    )
    assert "【過去話の失敗教訓（執筆時に最優先で回避）】" in out
    assert "deai" in out
    assert "AI定型表現を使わない" in out
    assert "第3話に発生・2回目" in out


def test_multiple_lessons_all_included_under_limit():
    comp = _composer()
    lessons = [
        {
            "dimension": "deai",
            "lesson_text": "教訓1",
            "severity": "medium",
            "occurrences": 1,
            "last_seen_episode": 1,
        },
        {
            "dimension": "hook",
            "lesson_text": "教訓2",
            "severity": "high",
            "occurrences": 3,
            "last_seen_episode": 5,
        },
    ]
    out = comp._format_audit_lessons(lessons, max_items=5, block_max_chars=800)
    assert "教訓1" in out
    assert "教訓2" in out


def test_max_items_truncates():
    comp = _composer()
    lessons = [
        {"dimension": "d", "lesson_text": f"教訓{i}", "severity": "m", "occurrences": 1, "last_seen_episode": i}
        for i in range(5)
    ]
    out = comp._format_audit_lessons(lessons, max_items=2, block_max_chars=10000)
    assert "教訓0" in out
    assert "教訓1" in out
    assert "教訓4" not in out


def test_block_max_chars_truncates():
    comp = _composer()
    long_text = "A" * 500
    lessons = [
        {"dimension": "d", "lesson_text": long_text, "severity": "m", "occurrences": 1, "last_seen_episode": 1},
        {"dimension": "d", "lesson_text": "B" * 500, "severity": "m", "occurrences": 1, "last_seen_episode": 2},
    ]
    out = comp._format_audit_lessons(lessons, max_items=10, block_max_chars=200)
    # 1 件目で上限に達し、2 件目は含まれない
    assert "B" * 500 not in out


def test_empty_lesson_text_skipped():
    comp = _composer()
    lessons = [
        {"dimension": "d", "lesson_text": "", "severity": "m", "occurrences": 1, "last_seen_episode": 1},
        {"dimension": "d", "lesson_text": "   ", "severity": "m", "occurrences": 1, "last_seen_episode": 1},
        {"dimension": "d", "lesson_text": "有効な教訓", "severity": "m", "occurrences": 1, "last_seen_episode": 1},
    ]
    out = comp._format_audit_lessons(lessons, max_items=10, block_max_chars=10000)
    assert "有効な教訓" in out
    # 空・空白のみはスキップされる（ヘッダだけの行は出力されない）


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
