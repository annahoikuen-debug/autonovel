"""
H8: 監査失敗教訓メモリ（Reflexion 型）。

監査不合格・警告通過時に発生した「失敗の教訓」を作品単位で永続化し、
次話執筆プロンプトへ注入することで、同一失敗の再発を防ぐ。

ライフサイクル:
  active（未解決） → graduated（同 dimension が合格で卒業） → archived（上限超過で最古からアーカイブ）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database.models_lessons import AuditLessonModel

logger = logging.getLogger(__name__)

#: book あたり active 教訓の上限。超過分は最古から archived へ。
DEFAULT_ACTIVE_MAX = 20
#: 注入する教訓の最大件数（プロンプト肥大化防止）。
DEFAULT_INJECT_MAX_ITEMS = 5
#: 注入ブロック全体の最大文字数。
DEFAULT_INJECT_BLOCK_MAX_CHARS = 800
#: 教訓 1 件の最大文字数。
DEFAULT_LESSON_MAX_CHARS = 200
#: 注入に必要な最小発生回数（1 で即時注入）。
DEFAULT_MIN_OCCURRENCES = 1


class AuditLessonRepository:
    """AuditLessonModel の非同期DBアクセス層。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _find_existing(
        self,
        book_id: int,
        dimension: str,
        lesson_text: str,
    ) -> AuditLessonModel | None:
        """同一 (book_id, dimension, lesson_text) の active レコードを探す。"""
        stmt = select(AuditLessonModel).where(
            AuditLessonModel.book_id == book_id,
            AuditLessonModel.dimension == dimension,
            AuditLessonModel.lesson_text == lesson_text,
            AuditLessonModel.status == "active",
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def record(
        self,
        book_id: int,
        episode_num: int,
        dimension: str,
        lesson_text: str,
        severity: str = "medium",
    ) -> AuditLessonModel:
        """教訓を記録する（upsert）。

        同一 (book_id, dimension, lesson_text) の active レコードがあれば
        occurrences += 1 / last_seen_episode 更新、無ければ insert する。
        """
        lesson_text = (lesson_text or "").strip()[:DEFAULT_LESSON_MAX_CHARS]
        if not lesson_text:
            raise ValueError("lesson_text is empty")

        existing = await self._find_existing(book_id, dimension, lesson_text)
        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.occurrences = int(existing.occurrences or 0) + 1
            existing.last_seen_episode = episode_num
            existing.updated_at = now
            existing.status = "active"  # 再発すれば active に戻す
            await self.db.flush()
            return existing

        # active 上限チェック：超過分は最古から archived へ
        try:
            from src.agents.audit_agent.config import get_lesson_active_max

            max_active = get_lesson_active_max()
        except Exception:
            max_active = DEFAULT_ACTIVE_MAX
        await self._enforce_active_max(book_id, max_active=max_active)

        record = AuditLessonModel(
            book_id=book_id,
            episode_num=episode_num,
            dimension=dimension,
            lesson_text=lesson_text,
            severity=severity,
            occurrences=1,
            status="active",
            first_seen_episode=episode_num,
            last_seen_episode=episode_num,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def _enforce_active_max(self, book_id: int, max_active: int = DEFAULT_ACTIVE_MAX) -> None:
        """active 教訓が max_active を超えたら、最古のものを archived にする。"""
        stmt = (
            select(AuditLessonModel)
            .where(AuditLessonModel.book_id == book_id, AuditLessonModel.status == "active")
            .order_by(AuditLessonModel.last_seen_episode.asc(), AuditLessonModel.created_at.asc())
        )
        res = await self.db.execute(stmt)
        actives = list(res.scalars().all())
        if len(actives) >= max_active:
            to_archive = actives[: len(actives) - max_active + 1]
            now = datetime.now(timezone.utc)
            for lesson in to_archive:
                lesson.status = "archived"
                lesson.updated_at = now
            await self.db.flush()

    async def graduate(self, book_id: int, dimension: str) -> int:
        """指定 dimension の active 教訓を graduated に更新。返り値は更新件数。"""
        stmt = select(AuditLessonModel).where(
            AuditLessonModel.book_id == book_id,
            AuditLessonModel.dimension == dimension,
            AuditLessonModel.status == "active",
        )
        res = await self.db.execute(stmt)
        lessons = list(res.scalars().all())
        now = datetime.now(timezone.utc)
        for lesson in lessons:
            lesson.status = "graduated"
            lesson.updated_at = now
        if lessons:
            await self.db.flush()
        return len(lessons)

    async def list_active(
        self,
        book_id: int,
        limit: int = DEFAULT_INJECT_MAX_ITEMS,
        min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    ) -> list[AuditLessonModel]:
        """active 教訓を話数降順（最新優先）で取得。"""
        stmt = (
            select(AuditLessonModel)
            .where(
                AuditLessonModel.book_id == book_id,
                AuditLessonModel.status == "active",
                AuditLessonModel.occurrences >= min_occurrences,
            )
            .order_by(AuditLessonModel.last_seen_episode.desc(), AuditLessonModel.created_at.desc())
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class AuditLessonService:
    """教訓メモリの生成・卒業・照合を一括管理するサービス。"""

    def __init__(self, repo: AuditLessonRepository):
        self.repo = repo

    async def record_from_audit(
        self,
        book_id: int,
        episode_num: int,
        failed_audits: Sequence[dict[str, Any]],
    ) -> list[AuditLessonModel]:
        """監査失敗結果から教訓を記録する。

        failed_audits の各要素は {"audit_id", "severity", "feedback", "error"} を持つ
        dict を想定。dimension は audit_id から、lesson_text は feedback を
        ルール圧縮（先頭 200字）して生成する。LLM は呼ばない。
        """
        recorded: list[AuditLessonModel] = []
        for audit in failed_audits or []:
            dimension = str(audit.get("audit_id") or "unknown")
            feedback = str(audit.get("feedback") or audit.get("error") or "").strip()
            severity = str(audit.get("severity") or "medium")
            if not feedback:
                continue
            try:
                lesson = await self.repo.record(
                    book_id=book_id,
                    episode_num=episode_num,
                    dimension=dimension,
                    lesson_text=feedback,
                    severity=severity,
                )
                recorded.append(lesson)
            except Exception:
                logger.warning("lesson record failed: audit_id=%s", dimension, exc_info=True)
        return recorded

    async def graduate_dimensions(
        self,
        book_id: int,
        passed_dimensions: Sequence[str],
    ) -> int:
        """合格した dimension の教訓を graduated にする。"""
        total = 0
        for dimension in passed_dimensions or []:
            total += await self.repo.graduate(book_id, str(dimension))
        return total

    async def get_active_lessons(
        self,
        book_id: int,
        limit: int = DEFAULT_INJECT_MAX_ITEMS,
        min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    ) -> list[AuditLessonModel]:
        """active 教訓を取得する（注入用）。"""
        return await self.repo.list_active(
            book_id=book_id, limit=limit, min_occurrences=min_occurrences
        )


__all__ = [
    "AuditLessonRepository",
    "AuditLessonService",
    "DEFAULT_ACTIVE_MAX",
    "DEFAULT_INJECT_MAX_ITEMS",
    "DEFAULT_INJECT_BLOCK_MAX_CHARS",
    "DEFAULT_LESSON_MAX_CHARS",
    "DEFAULT_MIN_OCCURRENCES",
]
