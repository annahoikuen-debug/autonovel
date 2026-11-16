from __future__ import annotations

from datetime import datetime

"""名シーン・名台詞モデル定義。"""

from sqlalchemy import Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleVector


class Masterpiece(Base):
    __tablename__ = "masterpieces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emotion_or_scene: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector_json: Mapped[list | None] = mapped_column(CompatibleVector, nullable=True)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
