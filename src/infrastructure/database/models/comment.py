from __future__ import annotations

from datetime import datetime

"""コメントモデル定義。"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), nullable=False)
    chapter_ep: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    author_name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("comments.id"), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
