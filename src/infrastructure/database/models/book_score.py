# src/infrastructure/database/models/book_score.py
"""BookScore ORM モデル"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base


class BookScore(Base):
    __tablename__ = "book_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    structure_score: Mapped[float] = mapped_column(Float, nullable=False)
    coherency_score: Mapped[float] = mapped_column(Float, nullable=False)
    factual_grounding_score: Mapped[float] = mapped_column(Float, nullable=False)
    visual_textual_synergy_score: Mapped[float] = mapped_column(Float, nullable=False)
    reader_experience_score: Mapped[float] = mapped_column(Float, nullable=False)
    specialist_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 8専門家スコア及び寄与度詳細
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)

    # リレーションシップ（必要に応じて）
    # book = relationship("Book", back_populates="scores")

    def __repr__(self):
        return f"<BookScore(book_id={self.book_id}, chapter={self.chapter_number}, overall={self.overall_score})>"
