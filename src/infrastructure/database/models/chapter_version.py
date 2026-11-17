from __future__ import annotations

from datetime import datetime

"""チャプターバージョンモデル定義。"""

from sqlalchemy import ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class ChapterVersion(Base):
    __tablename__ = "chapter_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), nullable=False)
    chapter_ep: Mapped[int] = mapped_column(Integer, nullable=False)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector_clock: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False)
    base_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chapter_versions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (  # type: ignore[assignment]
        Index("idx_chv_book_chap", "book_id", "chapter_ep"),
    )
