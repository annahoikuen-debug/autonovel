from __future__ import annotations

"""コメントモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    chapter_ep = Column(Integer, nullable=False)
    anchor_text = Column(Text, default="")
    author_name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(CompatibleDateTime, server_default=func.now())
