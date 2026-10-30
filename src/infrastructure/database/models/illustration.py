from __future__ import annotations

"""イラストレーションモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class Illustration(Base):
    __tablename__ = "illustrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    illustration_type = Column(String(50), nullable=False, default="cover")
    episode_number = Column(Integer, nullable=True)
    character_id = Column(Integer, nullable=True)
    model = Column(String(100), default="imagen-4.0-fast-generate-001")
    safety_level = Column(String(50), default="BLOCK_SOME")
    prompt = Column(Text, default="")
    image_url = Column(String(500), nullable=False)
    generation_time_ms = Column(Integer, default=0)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_illustrations_book_id", "book_id"),
        Index("idx_illustrations_book_type", "book_id", "illustration_type"),
    )
