from __future__ import annotations

"""保留パッチモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class PendingPatch(Base):
    __tablename__ = "pending_patches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    patch_type = Column(String(50), nullable=False)
    patch_content = Column(Text, nullable=False)
    ab_test_result = Column(Text, default="{}")
    status = Column(String(20), default="pending")
    reviewed_at = Column(CompatibleDateTime)
    created_at = Column(CompatibleDateTime, server_default=func.now())
