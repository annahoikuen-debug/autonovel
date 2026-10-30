from __future__ import annotations

"""最適化履歴モデル定義。"""

from sqlalchemy import Column, Integer, Text, ForeignKey, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class OptimizationHistory(Base):
    __tablename__ = "optimization_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    report_json = Column(Text, default="{}")
    created_at = Column(CompatibleDateTime, server_default=func.now())
