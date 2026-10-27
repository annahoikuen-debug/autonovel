"""パッチ適用/スキップイベントが発火することの回帰テスト。

W4 Step 11（``src/agents/audit_agent.py``）の回帰テスト。
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

import pytest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.audit_agent import AuditAgent  # noqa: E402


class _Conflict:
    def __init__(self, current_value: str, suggested_value: str) -> None:
        self.current_value = current_value
        self.suggested_value = suggested_value


class _Report:
    is_acceptable = False
    final_score = 40.0

    def __init__(self, conflicts: list[Any] | None = None) -> None:
        self.conflicts = conflicts or []
        self.qualitative = None


async def test_skipped_event_on_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_LOCAL_PATCH", "0")
    agent = AuditAgent()
    assert await agent.try_local_patch("本文。") is None
    events = agent.drain_events()
    skipped = [e for e in events if e["event"] == "audit.patch.skipped"]
    assert len(skipped) == 1
    assert set(skipped[0]) == {"event", "reason"}
    assert skipped[0]["reason"] == "local_patch_disabled"
    assert "audit.patch.applied" not in [e["event"] for e in events]


async def test_skipped_event_on_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_LOCAL_PATCH", "1")
    agent = AuditAgent()
    assert await agent.try_local_patch("") is None
    skipped = [e for e in agent.drain_events() if e["event"] == "audit.patch.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "empty_drafted_text"


async def test_applied_event_carries_four_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_LOCAL_PATCH", "1")
    agent = AuditAgent()
    agent._audit_llm = None
    report = _Report([_Conflict("AAA", "BBB")])

    out = await agent.try_local_patch("AAA が光った。", unified_report=report)
    assert out is not None
    events = agent.drain_events()
    applied = [e for e in events if e["event"] == "audit.patch.applied"]
    assert len(applied) == 1
    assert set(applied[0]) == {"event", "strategy", "replacements", "text_length", "triage_level"}
    assert applied[0]["strategy"] == "safe_replace"
    assert applied[0]["replacements"] == 1
    assert applied[0]["text_length"] == len(out["text"])
    assert "audit.patch.skipped" not in [e["event"] for e in events]


async def test_exactly_one_event_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """1 回の ``try_local_patch`` 呼び出しで applied / skipped は高々1回。"""
    monkeypatch.setenv("ENABLE_AUDIT_LOCAL_PATCH", "1")
    agent = AuditAgent()
    agent._audit_llm = None

    assert await agent.try_local_patch("AAA が光った。", unified_report=_Report([_Conflict("AAA", "BBB")])) is not None
    assert await agent.try_local_patch("何もない本文。", unified_report=_Report()) is None

    events = agent.drain_events()
    assert len([e for e in events if e["event"] == "audit.patch.applied"]) == 1
    assert len([e for e in events if e["event"] == "audit.patch.skipped"]) == 1


def test_event_ring_buffer_bounded() -> None:
    agent = AuditAgent()
    for i in range(600):
        agent.emit_event("audit.tick", {"i": i})
    assert len(agent.drain_events()) <= 500
