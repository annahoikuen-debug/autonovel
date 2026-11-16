from __future__ import annotations

from datetime import datetime

"""監査課題モデル定義。"""

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class AuditIssue(Base):
    __tablename__ = "audit_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 作品単位の監査課題一覧は hot filter
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ep_num: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_past: Mapped[str] = mapped_column(Text, default="")
    evidence_current: Mapped[str] = mapped_column(Text, default="")
    constraint_for_next_ep: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolved_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())

    # Review linkage fields
    patch_review_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patch_reviews.id"), nullable=True)
    user_resolution: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # USER_ACCEPTED, USER_REJECTED, USER_MODIFIED
    resolved_at: Mapped[datetime | None] = mapped_column(CompatibleDateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
