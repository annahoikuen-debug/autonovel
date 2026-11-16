from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""CharacterArc ORM モデル定義。

キャラクターアーク（成長曲線）情報を永続化する。
"""


class CharacterArc(Base):
    __tablename__ = "character_arcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    arc_name: Mapped[str | None] = mapped_column(String(100))
    arc_stages: Mapped[str] = mapped_column(Text, default="[]")
    current_stage_index: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
