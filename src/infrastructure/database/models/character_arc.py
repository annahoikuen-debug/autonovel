from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""CharacterArc ORM モデル定義。

キャラクターアーク（成長曲線）情報を永続化する。
"""


class CharacterArc(Base):
    __tablename__ = "character_arcs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    arc_name = Column(String(100))
    arc_stages = Column(Text, default="[]")
    current_stage_index = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    created_at = Column(CompatibleDateTime, server_default=func.now())
