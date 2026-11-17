from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""イラストレーションモデル定義。"""


class Illustration(Base):
    __tablename__ = "illustrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    illustration_type: Mapped[str] = mapped_column(String(50), nullable=False, default="cover")
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    character_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(String(100), default="imagen-4.0-fast-generate-001")
    safety_level: Mapped[str] = mapped_column(String(50), default="BLOCK_SOME")
    prompt: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    generation_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (  # type: ignore[assignment]
        Index("idx_illustrations_book_id", "book_id"),
        Index("idx_illustrations_book_type", "book_id", "illustration_type"),
    )
