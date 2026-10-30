from __future__ import annotations

"""キャラクター関係性モデル定義。

キャラクター間関係性モデル（永続化対応）
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, func, UniqueConstraint, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    char_a = Column(String(100), nullable=False)
    char_b = Column(String(100), nullable=False)
    affection = Column(Float, default=0.0, nullable=False)
    trust = Column(Float, default=0.0, nullable=False)
    tension = Column(Float, default=0.0, nullable=False)
    depth = Column(Float, default=0.0, nullable=False)
    dynamics_state = Column(String(50), default="strangers", nullable=False)
    last_interaction_ep = Column(Integer, default=0, nullable=False)
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("book_id", "char_a", "char_b", name="uq_char_rel"),
        Index("ix_char_rel_book", "book_id"),
    )
