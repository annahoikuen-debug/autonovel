from __future__ import annotations

"""キャラクター関係性履歴モデル定義。

キャラクター関係性履歴モデル（時系列推移ログ）
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class RelationshipHistory(Base):
    __tablename__ = "relationship_histories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    relationship_id = Column(
        Integer,
        ForeignKey("character_relationships.id", ondelete="CASCADE"),
        nullable=False,
    )
    episode_num = Column(Integer, nullable=False)
    affection = Column(Float, nullable=False)
    trust = Column(Float, nullable=False)
    tension = Column(Float, nullable=False)
    depth = Column(Float, nullable=False)
    dynamics_state = Column(String(50), nullable=False)
    trigger_event = Column(String(255), default="")
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_rel_history_rel_id", "relationship_id"),
        Index("ix_rel_history_ep", "episode_num"),
    )
