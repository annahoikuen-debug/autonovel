from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""Foreshadowing ORM モデル定義。

伏線情報を永続化する。
"""


class Foreshadowing(Base):
    __tablename__ = "foreshadowing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, default=1, nullable=False)
    ep_num = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)
    description = Column(Text)
    location = Column(String(100))
    payoff_ep = Column(Integer, nullable=True)
    payoff_location = Column(String(100), nullable=True)
    strength = Column(Float, default=1.0)
    fulfilled = Column(Boolean, default=False)
    created_at = Column(CompatibleDateTime, server_default=func.now())
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("book_id", "branch_id", "ep_num", "type", name="uq_foreshadowing"),
    )
