from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleJSON


"""Character ORM モデル定義。

キャラクター情報を永続化する。
"""


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str | None] = mapped_column(String(50))
    personality: Mapped[str] = mapped_column(String(500), default="")
    ability: Mapped[str] = mapped_column(String(500), default="")
    registry_data: Mapped[str | None] = mapped_column(Text)
    voice_profile_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
