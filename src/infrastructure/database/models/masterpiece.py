from __future__ import annotations

"""名シーン・名台詞モデル定義。"""

from sqlalchemy import Column, Integer, String, Text, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleVector


class Masterpiece(Base):
    __tablename__ = "masterpieces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    emotion_or_scene = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    vector_json = Column(CompatibleVector, nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())
