from __future__ import annotations

"""パッチレビューモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.models.patch_review_status import PatchReviewStatus
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class PatchReview(Base):
    __tablename__ = "patch_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    ep_num = Column(Integer, nullable=False)
    patch_type = Column(String(50), nullable=False)  # config, prompt, setting
    original_content = Column(Text, nullable=False)
    proposed_content = Column(Text, nullable=False)
    diff_json = Column(Text, default="{}")
    status = Column(String(20), default=PatchReviewStatus.GENERATED, nullable=False)
    reviewer_id = Column(String(100), nullable=True)
    reviewed_at = Column(CompatibleDateTime, nullable=True)
    review_comment = Column(Text, default="")
    audit_issue_ids = Column(CompatibleJSON, default=[])
    learning_metadata = Column(CompatibleJSON, default={})
    created_at = Column(CompatibleDateTime, server_default=func.now())
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_patch_reviews_book_ep", "book_id", "ep_num"),
        Index("idx_patch_reviews_status", "status"),
    )
