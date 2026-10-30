from __future__ import annotations

"""カスタムスタイルモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class CustomStyle(Base):
    __tablename__ = "custom_styles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    instruction = Column(Text)
    score = Column(Integer, default=0)
    analysis = Column(Text)
    created_at = Column(CompatibleDateTime, server_default=func.now())
