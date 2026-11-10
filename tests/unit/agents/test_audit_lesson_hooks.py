"""H8: `AuditAgent._record_lessons` / `_graduate_lessons` フックの単体テスト。

セッション未取得・flag OFF 時は fail-open で記録/卒業を行わないことを検証。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from src.agents.audit_agent import AuditAgent


class _DummyRepo:
    """session を持つダミーリポジトリ。"""


def _make_agent(monkeypatch, session=None):
    """flag ON で AuditAgent を作成し、repo.session を注入する。"""
    monkeypatch.setenv("ENABLE_AUDIT_LESSONS", "1")
    agent = AuditAgent()
    agent.repo = _DummyRepo()
    agent.repo.session = session
    return agent


async def test_record_lessons_session_none_is_noop(monkeypatch):
    """セッション未取得時は記録をスキップ（例外にならない）。"""
    agent = _make_agent(monkeypatch, session=None)
    # 例外が出ず、正常終了することだけを確認
    await agent._record_lessons(
        book_id=1,
        ep_num=1,
        failed_audits=[{"audit_id": "deai", "severity": "medium", "feedback": "AI感"}],
    )


async def test_record_lessons_flag_off_is_noop(monkeypatch):
    """ENABLE_AUDIT_LESSONS=OFF 時は記録を行わない。"""
    monkeypatch.delenv("ENABLE_AUDIT_LESSONS", raising=False)
    agent = _make_agent(monkeypatch, session=MagicMock())
    await agent._record_lessons(
        book_id=1,
        ep_num=1,
        failed_audits=[{"audit_id": "deai", "severity": "medium", "feedback": "AI感"}],
    )


async def test_graduate_lessons_session_none_is_noop(monkeypatch):
    """セッション未取得時は卒業処理をスキップ。"""
    agent = _make_agent(monkeypatch, session=None)
    await agent._graduate_lessons(book_id=1, passed_dimensions=["deai", "hook"])


async def test_record_lessons_with_session_executes_db(monkeypatch):
    """セッションあり・flag ON で DB 操作（execute/flush）が実行される。"""
    session = MagicMock()
    session.flush = AsyncMock()
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)
    session.add = MagicMock()
    agent = _make_agent(monkeypatch, session=session)

    await agent._record_lessons(
        book_id=7,
        ep_num=3,
        failed_audits=[{"audit_id": "deai", "severity": "medium", "feedback": "AI感"}],
    )

    assert session.execute.called, "_find_existing で session.execute が呼ばれるべき"
    assert session.flush.called, "record で session.flush が呼ばれるべき"
    assert session.add.called, "record で session.add が呼ばれるべき（新規insert）"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
