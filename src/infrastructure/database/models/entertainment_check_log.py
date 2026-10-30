from __future__ import annotations

"""エンタメチェックログモデル定義。"""

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class EntertainmentCheckLog(Base):
    __tablename__ = "entertainment_check_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    ep_num = Column(Integer, nullable=False)
    interest_score = Column(Integer, nullable=True)
    physiological_reaction = Column(String(255), nullable=True)
    would_continue_reading = Column(Boolean, nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (Index("idx_entertainment_check_log_book_ep", "book_id", "ep_num"),)
