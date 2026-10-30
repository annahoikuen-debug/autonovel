from __future__ import annotations

"""コスト消費ログモデル定義。"""

from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, func, Index
from src.infrastructure.database.models.base_orm import Base


class CostLogModel(Base):
    """個別トークン消費・コスト記録ログ。

    どのエージェントがどのモデルで何トークン消費し、いくら費用が発生したかを記録する。
    """

    __tablename__ = "cost_consumption_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=True)
    agent_name = Column(String(100), nullable=False)
    model_name = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_cost_log_book_id", "book_id"),
        Index("idx_cost_log_agent_name", "agent_name"),
        Index("idx_cost_log_timestamp", "timestamp"),
    )
