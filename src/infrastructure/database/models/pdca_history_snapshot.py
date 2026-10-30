from __future__ import annotations

"""PDCA 履歴スナップショットモデル定義。"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class PDCAHistorySnapshot(Base):
    __tablename__ = "pdca_history_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=False)
    cycle_number = Column(Integer, nullable=False)
    initial_score = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False)
    score_delta = Column(Float, nullable=False)
    improved_percentage = Column(Float, nullable=False)
    lowest_dimension = Column(String(100), nullable=False)
    directives = Column(CompatibleJSON, nullable=False, default=list)
    history = Column(CompatibleJSON, nullable=False, default=list)
    converged = Column(Boolean, nullable=False, default=False)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_pdca_history_book_chap", "book_id", "chapter_number"),
    )
