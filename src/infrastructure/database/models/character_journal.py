from __future__ import annotations

from datetime import datetime

"""キャラクター日記モデル定義。

キャラクター日記モデル（多視点ログ永続化対応）
"""

from sqlalchemy import ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class CharacterJournal(Base):
    __tablename__ = "character_journals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    character_name: Mapped[str] = mapped_column(String(100), nullable=False)
    episode_num: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_text: Mapped[str] = mapped_column(Text, nullable=False)
    emotional_state: Mapped[str] = mapped_column(String(100), default="")
    secret_thought: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_char_journal_book_char", "book_id", "character_name"),
        Index("ix_char_journal_ep", "book_id", "episode_num"),
    )
