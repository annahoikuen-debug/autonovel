from __future__ import annotations

"""内部状態モデル定義。"""

from sqlalchemy import Column, Integer, String, Text, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class InternalState(Base):
    __tablename__ = "internal_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(200), nullable=False, unique=True)
    value = Column(Text, default="")
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())
