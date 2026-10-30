from __future__ import annotations

"""ナラティブ指標モデル定義。"""

from sqlalchemy import Column, Integer, String, ForeignKey, Float, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class NarrativeMetric(Base):
    __tablename__ = "narrative_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    recorded_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_narrative_metrics_book_id", "book_id"),
        Index("idx_narrative_metrics_chapter_id", "chapter_id"),
        Index("idx_narrative_metrics_metric_name", "metric_name"),
    )
