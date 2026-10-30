from __future__ import annotations

"""設定バージョンモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func, UniqueConstraint, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class SettingVersion(Base):
    __tablename__ = "setting_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    snapshot_json = Column(Text, nullable=False)  # Full settings snapshot
    base_version_id = Column(Integer, ForeignKey("setting_versions.id"), nullable=True)
    change_summary = Column(Text, default="")
    created_by = Column(String(100), nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("book_id", "version_number", name="uq_setting_versions_book_ver"),
        Index("idx_setting_versions_book", "book_id"),
    )
