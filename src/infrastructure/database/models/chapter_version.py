from __future__ import annotations

"""チャプターバージョンモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class ChapterVersion(Base):
    __tablename__ = "chapter_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    chapter_ep = Column(Integer, nullable=False)
    user_name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    vector_clock = Column(CompatibleJSON, nullable=False)
    base_version_id = Column(Integer, ForeignKey("chapter_versions.id"), nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (Index("idx_chv_book_chap", "book_id", "chapter_ep"),)
