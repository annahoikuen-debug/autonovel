from __future__ import annotations

"""監査課題モデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class AuditIssue(Base):
    __tablename__ = "audit_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 作品単位の監査課題一覧は hot filter
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    ep_num = Column(Integer, nullable=False)
    category = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    evidence_past = Column(Text, default="")
    evidence_current = Column(Text, default="")
    constraint_for_next_ep = Column(Text, default="")
    status = Column(String(20), default="open")
    resolved_note = Column(Text, default="")
    created_at = Column(CompatibleDateTime, server_default=func.now())

    # Review linkage fields
    patch_review_id = Column(Integer, ForeignKey("patch_reviews.id"), nullable=True)
    user_resolution = Column(
        String(50), nullable=True
    )  # USER_ACCEPTED, USER_REJECTED, USER_MODIFIED
    resolved_at = Column(CompatibleDateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
