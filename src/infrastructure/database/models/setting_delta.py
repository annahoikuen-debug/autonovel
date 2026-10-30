from __future__ import annotations

"""設定差分モデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class SettingDelta(Base):
    __tablename__ = "setting_deltas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    field_path = Column(String(500), nullable=False)  # e.g., "world_rules.magic_system.mana_cost"
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    delta_type = Column(String(50), nullable=False)  # MANUAL, AUTO_REPAIR, USER_CORRECTION
    source = Column(String(50), nullable=False)  # user, audit_agent, bible_service
    merged_to_graphrag = Column(Boolean, default=False, nullable=False)
    merged_at = Column(CompatibleDateTime, nullable=True)
    patch_review_id = Column(Integer, ForeignKey("patch_reviews.id"), nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_setting_deltas_book_field", "book_id", "field_path"),
        Index("idx_setting_deltas_merged", "merged_to_graphrag"),
    )
