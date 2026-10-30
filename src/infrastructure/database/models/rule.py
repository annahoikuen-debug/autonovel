from __future__ import annotations

"""ルールモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_word = Column(String(200), nullable=False)
    instruction = Column(Text, nullable=False)
    level = Column(String(50), default="global")
    domain = Column(String(50), default="all")
    character_name = Column(String(100))
    status = Column(String(20), default="active")
    created_at = Column(CompatibleDateTime, server_default=func.now())
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())
