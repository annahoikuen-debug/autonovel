"""AuditRun 永続化テスト (M0: 計測基盤)。

UnifiedAuditor.audit() に db_session を渡したとき、
AuditRun への書き込みが fail-open で行われることを検証する。
"""

from __future__ import annotations

import hashlib

from src.agents.specialists.unified_auditor import UnifiedAuditor
from tests.mocks.llm_adapter import MockLLMAdapter


_TEST_TEXT = (
    "これはテスト用の本文です。十分な長さを持たせるために、複数の文章を含めておきます。"
)


class _FakeSession:
    """add / commit / rollback を記録する最小限の DB セッションモック。"""

    def __init__(self, fail: bool = False) -> None:
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.fail = fail

    def add(self, obj):  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("db write failure")
        self.added.append(obj)

    def commit(self):  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("db commit failure")
        self.committed = True

    def rollback(self):  # type: ignore[no-untyped-def]
        self.rolled_back = True


def _make_auditor() -> UnifiedAuditor:
    return UnifiedAuditor(llm_gateway=MockLLMAdapter())


async def test_audit_persistence_skipped_when_no_session():
    """db_session=None なら書き込みをスキップし、監査結果は正常に返る。"""
    auditor = _make_auditor()
    report = await auditor.audit(_TEST_TEXT)
    assert report is not None
    assert isinstance(report.final_score, float)
    assert isinstance(report.is_acceptable, bool)


async def test_audit_persistence_writes_audit_run():
    """db_session を渡すと AuditRun が add / commit され、属性が正しい。"""
    auditor = _make_auditor()
    session = _FakeSession()
    report = await auditor.audit(
        _TEST_TEXT,
        db_session=session,
        book_id=1,
        ep_num=2,
    )
    assert session.committed is True
    assert session.rolled_back is False
    assert len(session.added) == 1

    run = session.added[0]
    assert run.book_id == 1
    assert run.ep_num == 2
    assert round(run.final_score, 1) == report.final_score
    assert run.is_passed == report.is_acceptable
    assert run.q_cliche_count >= 0
    assert 0.0 <= run.q_rhythm <= 100.0
    assert run.judge_mode == "single"
    assert run.gate_version == "1.0"
    assert run.text_hash == hashlib.sha256(_TEST_TEXT.encode("utf-8")).hexdigest()
    assert run.text_snapshot == _TEST_TEXT


async def test_audit_persistence_fail_open_on_session_error():
    """セッション書き込み失敗時も監査結果は正常に返る（fail-open）。"""
    auditor = _make_auditor()
    session = _FakeSession(fail=True)
    report = await auditor.audit(
        _TEST_TEXT,
        db_session=session,
    )
    assert session.rolled_back is True
    assert report is not None
    assert isinstance(report.final_score, float)
    assert isinstance(report.is_acceptable, bool)


async def test_audit_persistence_deterministic_hash():
    """同一テキストなら text_hash が不変、異なるテキストなら変わる。"""
    auditor = _make_auditor()
    session1 = _FakeSession()
    session2 = _FakeSession()
    await auditor.audit(_TEST_TEXT, db_session=session1)
    await auditor.audit(_TEST_TEXT, db_session=session2)
    assert session1.added[0].text_hash == session2.added[0].text_hash

    session3 = _FakeSession()
    await auditor.audit(_TEST_TEXT + " 追加文。", db_session=session3)
    assert session3.added[0].text_hash != session1.added[0].text_hash
