from __future__ import annotations

"""キャラクター日記モデル定義。

キャラクター日記モデル（多視点ログ永続化対応）
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class CharacterJournal(Base):
    __tablename__ = "character_journals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    character_name = Column(String(100), nullable=False)
    episode_num = Column(Integer, nullable=False)
    entry_text = Column(Text, nullable=False)
    emotional_state = Column(String(100), default="")
    secret_thought = Column(Text, default="")
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_char_journal_book_char", "book_id", "character_name"),
        Index("ix_char_journal_ep", "book_id", "episode_num"),
    )
