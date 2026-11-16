from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""Chapter ORM モデル定義。

章（エピソード）のコンテンツとメタデータを永続化する。
"""


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    branch_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    ep_num: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str | None] = mapped_column(Text)
    score_story: Mapped[int | None] = mapped_column(Integer)
    killer_phrase: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    world_state: Mapped[str | None] = mapped_column(Text)
    trinity_review_log: Mapped[str | None] = mapped_column(Text)
    ai_insight: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
    tension_delta: Mapped[int] = mapped_column(Integer, default=0)
    qol_delta: Mapped[int] = mapped_column(Integer, default=0)
    is_anchor: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_jpy: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit_ratio: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (UniqueConstraint("book_id", "branch_id", "ep_num", name="uq_chapters_book_branch_ep"),)
