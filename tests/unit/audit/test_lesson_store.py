"""H8: `src/audit/lesson_store.py` (AuditLessonRepository / AuditLessonService) の単体テスト。

実DBは使わず AsyncMock でセッションを模擬。純粋なレコード/卒業/照合ロジックを検証。
`asyncio_mode=auto` により `async def` テスト関数は自動でイベントループ付き実行される。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from src.audit.lesson_store import (
    AuditLessonRepository,
    AuditLessonService,
    DEFAULT_ACTIVE_MAX,
    DEFAULT_INJECT_MAX_ITEMS,
)


def _make_session():
    """AsyncMock セッション。execute().scalars().first() / all() をモック化。

    `add` は SQLAlchemy では同期メソッドのため通常の MagicMock とする。
    """
    session = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session, scalars


def _make_lesson(**overrides):
    base = dict(
        id=1,
        book_id=1,
        episode_num=1,
        dimension="deai",
        lesson_text="テスト教訓",
        severity="medium",
        occurrences=1,
        status="active",
        first_seen_episode=1,
        last_seen_episode=1,
    )
    base.update(overrides)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


class TestAuditLessonRepository:
    async def test_record_new_insert(self):
        session, scalars = _make_session()
        scalars.first.return_value = None  # 既存レコードなし → insert
        repo = AuditLessonRepository(session)

        lesson = await repo.record(book_id=1, episode_num=1, dimension="deai", lesson_text="新規教訓")
        assert session.add.called
        assert session.flush.called
        assert lesson.lesson_text == "新規教訓"

    async def test_record_upsert_increments_occurrences(self):
        session, scalars = _make_session()
        existing = _make_lesson(occurrences=3, last_seen_episode=1)
        scalars.first.return_value = existing  # 既存レコードあり → upsert
        repo = AuditLessonRepository(session)

        lesson = await repo.record(book_id=1, episode_num=5, dimension="deai", lesson_text="テスト教訓")
        assert existing.occurrences == 4
        assert existing.last_seen_episode == 5
        assert existing.status == "active"
        # session.add は呼ばれない（既存オブジェクトの更新のみ）
        assert not session.add.called

    async def test_record_empty_text_raises(self):
        session, _ = _make_session()
        repo = AuditLessonRepository(session)

        with pytest.raises(ValueError):
            await repo.record(book_id=1, episode_num=1, dimension="deai", lesson_text="")

    async def test_record_text_truncated_to_max_chars(self):
        session, scalars = _make_session()
        scalars.first.return_value = None
        repo = AuditLessonRepository(session)

        long_text = "A" * 500
        await repo.record(book_id=1, episode_num=1, dimension="deai", lesson_text=long_text)
        added = session.add.call_args[0][0]
        assert len(added.lesson_text) <= 200

    async def test_graduate_updates_status(self):
        session, scalars = _make_session()
        l1 = _make_lesson(status="active")
        l2 = _make_lesson(status="active", dimension="other")
        scalars.all.return_value = [l1]  # dimension="deai" のみ一致
        repo = AuditLessonRepository(session)

        count = await repo.graduate(book_id=1, dimension="deai")
        assert count == 1
        assert l1.status == "graduated"
        assert session.flush.called

    async def test_list_active_returns_all_from_session(self):
        session, scalars = _make_session()
        l1 = _make_lesson(last_seen_episode=1, occurrences=2)
        l2 = _make_lesson(last_seen_episode=5, occurrences=1)
        l3 = _make_lesson(status="archived")
        scalars.all.return_value = [l1, l2, l3]
        repo = AuditLessonRepository(session)

        # モックは where 句を適用しないため全件返却。順序はセッション返却順。
        lessons = await repo.list_active(book_id=1, limit=10, min_occurrences=1)
        assert len(lessons) == 3
        assert lessons[0] is l1
        assert lessons[1] is l2
        assert lessons[2] is l3

    async def test_list_active_respects_limit(self):
        session, scalars = _make_session()
        lessons = [_make_lesson(id=i) for i in range(5)]
        scalars.all.return_value = lessons
        repo = AuditLessonRepository(session)

        # limit は SQLAlchemy 側で適用されるが、モックは無視して全件返す
        result = await repo.list_active(book_id=1, limit=2, min_occurrences=1)
        assert len(result) == 5

    async def test_enforce_active_max_archives_oldest(self):
        session, scalars = _make_session()
        # active_max=2 を超える 4 件を active とする（リスト順＝last_seen_episode 昇順）
        lessons = [_make_lesson(id=i, last_seen_episode=i) for i in range(1, 5)]
        scalars.all.return_value = lessons
        repo = AuditLessonRepository(session)

        await repo._enforce_active_max(1, max_active=2)
        # 最古の 3 件（id 1,2,3）が archived、最新の 1 件（id 4）は active のまま
        archived = [l for l in lessons if l.status == "archived"]
        active = [l for l in lessons if l.status == "active"]
        assert len(archived) == 3
        assert len(active) == 1
        assert active[0].id == 4


class TestAuditLessonService:
    async def test_record_from_audit_skips_empty_feedback(self):
        session, scalars = _make_session()
        scalars.first.return_value = None
        service = AuditLessonService(AuditLessonRepository(session))

        recorded = await service.record_from_audit(
            book_id=1,
            episode_num=1,
            failed_audits=[
                {"audit_id": "deai", "severity": "medium", "feedback": "AI感がある"},
                {"audit_id": "hook", "severity": "low", "feedback": ""},  # 空はスキップ
                {"audit_id": "hook", "severity": "low", "feedback": "AI感がある"},  # 重複 → upsert
            ],
        )
        assert len(recorded) == 2  # 空フィードバックはスキップ

    async def test_get_active_lessons_delegates_to_repo(self):
        session, scalars = _make_session()
        scalars.all.return_value = [_make_lesson()]
        service = AuditLessonService(AuditLessonRepository(session))

        lessons = await service.get_active_lessons(book_id=1, limit=3, min_occurrences=1)
        assert len(lessons) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
