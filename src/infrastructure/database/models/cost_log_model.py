from __future__ import annotations

from datetime import datetime

"""コスト消費ログモデル定義。"""

from sqlalchemy import DateTime, ForeignKey, Float, Integer, String, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base


class CostLogModel(Base):
    """個別トークン消費・コスト記録ログ。

    どのエージェントがどのモデルで何トークン消費し、いくら費用が発生したかを記録する。
    """

    __tablename__ = "cost_consumption_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (  # type: ignore[assignment]
        Index("idx_cost_log_book_id", "book_id"),
        Index("idx_cost_log_agent_name", "agent_name"),
        Index("idx_cost_log_timestamp", "timestamp"),
    )
