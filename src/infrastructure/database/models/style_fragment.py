from __future__ import annotations

"""スタイルフラグメントモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleVector


class StyleFragment(Base):
    __tablename__ = "style_fragments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    embedding_json = Column(CompatibleVector, nullable=True)
    origin = Column(String(50), default="Master")
    created_at = Column(CompatibleDateTime, server_default=func.now())
