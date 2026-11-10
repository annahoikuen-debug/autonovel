"""AuditLessonModel - 監査失敗教訓の永続化モデル (H8 Phase E1).

各話の監査不合格・警告通過時に発生した「失敗の教訓」を作品単位で保存する。
Reflexion 型の改稿ループにおいて、同一失敗の話横断再発を防ぐために次話執筆プロンプト
へ注入される。

Active → Graduated（同 dimension が合格で卒業） → Archived（上限超過で最古からアーカイブ）
のライフサイクルを持つ。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from src.infrastructure.database.models.base_orm import Base


class AuditLessonModel(Base):
    """監査失敗教訓モデル。

    Attributes:
        id: 教訓の一意識別子
        book_id: 所属作品ID（booksテーブル外部キー、CASCADE 削除）
        episode_num: 初出の話数
        dimension: 監査軸（structure / coherency / factual / cliche / hook / character 等）
        lesson_text: 教訓本文（最大 200字、ルール圧縮または LLM 要約）
        severity: 重要度（critical / high / medium / low）
        occurrences: 同 dimension の再発回数（注入閾値判定に使用）
        status: active | graduated | archived
        first_seen_episode: 初出話数
        last_seen_episode: 最終再発話数
        created_at / updated_at: タイムスタンプ
    """

    __tablename__ = "audit_lessons"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    episode_num = Column(Integer, nullable=False, index=True)
    dimension = Column(String(64), nullable=False, index=True)
    lesson_text = Column(Text, nullable=False)
    severity = Column(String(16), nullable=False, default="medium")
    occurrences = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="active", index=True)
    first_seen_episode = Column(Integer, nullable=False)
    last_seen_episode = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
