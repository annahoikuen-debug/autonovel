from __future__ import annotations

"""コスト記録モデル定義。"""

from sqlalchemy import Column, Integer, String, ForeignKey, Float, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class CostRecord(Base):
    __tablename__ = "cost_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    branch_id = Column(Integer, nullable=False, default=1)
    task_type = Column(String(50), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    est_cost_usd = Column(Float, nullable=False, default=0.0)
    ep_num = Column(Integer, nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_cost_record_book_id", "book_id"),
        Index("idx_cost_record_branch_id", "branch_id"),
    )
