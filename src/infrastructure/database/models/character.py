from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


"""Character ORM モデル定義。

キャラクター情報を永続化する。
"""


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100))
    role = Column(String(50))
    personality = Column(String(500), default="")
    ability = Column(String(500), default="")
    registry_data = Column(Text)
    voice_profile_json = Column(CompatibleJSON, nullable=True)
