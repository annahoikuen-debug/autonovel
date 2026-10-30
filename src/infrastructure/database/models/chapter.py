from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""Chapter ORM モデル定義。

章（エピソード）のコンテンツとメタデータを永続化する。
"""


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    branch_id = Column(Integer, default=1, nullable=False, index=True)
    ep_num = Column(Integer, nullable=False)
    title = Column(String(200))
    content = Column(Text)
    score_story = Column(Integer)
    killer_phrase = Column(String(500))
    summary = Column(Text)
    world_state = Column(Text)
    trinity_review_log = Column(Text)
    ai_insight = Column(Text)
    created_at = Column(CompatibleDateTime, server_default=func.now())
    tension_delta = Column(Integer, default=0)
    qol_delta = Column(Integer, default=0)
    is_anchor = Column(Boolean, default=False)
    cost_jpy = Column(Float, default=0.0)
    cache_hit_ratio = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("book_id", "branch_id", "ep_num", name="uq_chapters_book_branch_ep"),
    )
