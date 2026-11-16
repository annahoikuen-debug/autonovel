from __future__ import annotations

from datetime import datetime

"""保留パッチモデル定義。"""

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class PendingPatch(Base):
    __tablename__ = "pending_patches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    patch_type: Mapped[str] = mapped_column(String(50), nullable=False)
    patch_content: Mapped[str] = mapped_column(Text, nullable=False)
    ab_test_result: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(CompatibleDateTime)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
