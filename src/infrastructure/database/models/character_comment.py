from __future__ import annotations

"""キャラクターコメントモデル定義。

キャラクターコメントモデル（SNS風リアクション永続化対応）
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class CharacterComment(Base):
    __tablename__ = "character_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    character_name = Column(String(100), nullable=False)
    episode_num = Column(Integer, nullable=False)
    comment_text = Column(Text, nullable=False)
    topic = Column(String(100), default="")
    sentiment = Column(String(50), default="neutral")
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_char_comment_book_char", "book_id", "character_name"),
        Index("ix_char_comment_ep", "book_id", "episode_num"),
    )
