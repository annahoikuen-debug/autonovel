from __future__ import annotations

"""マルチメディア成果物モデル定義。

Multimedia 機能 (Phase 7) で生成された成果物のメタデータ。
"""

from sqlalchemy import Column, Integer, String, Text, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class MultimediaArtifact(Base):
    __tablename__ = "multimedia_artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, nullable=False)
    asset_type = Column(String(50), nullable=False)
    format = Column(String(50), nullable=False)
    file_path = Column(String(1024), nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_multimedia_artifacts_book_id", "book_id"),
        Index("ix_multimedia_artifacts_asset_type", "asset_type"),
    )
