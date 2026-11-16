from __future__ import annotations

from datetime import datetime

"""キャラクター関係性モデル定義。

キャラクター間関係性モデル（永続化対応）
"""

from sqlalchemy import Float, ForeignKey, Integer, String, func, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    char_a: Mapped[str] = mapped_column(String(100), nullable=False)
    char_b: Mapped[str] = mapped_column(String(100), nullable=False)
    affection: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trust: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tension: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    depth: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dynamics_state: Mapped[str] = mapped_column(String(50), default="strangers", nullable=False)
    last_interaction_ep: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("book_id", "char_a", "char_b", name="uq_char_rel"),
        Index("ix_char_rel_book", "book_id"),
    )
