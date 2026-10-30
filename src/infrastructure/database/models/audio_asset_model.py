from __future__ import annotations

from datetime import datetime

"""オーディオアセットモデル定義。"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func, Index
from src.infrastructure.database.models.base_orm import Base


class AudioAssetModel(Base):
    __tablename__ = "audio_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_num = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    file_size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audio_assets_book_ep", "book_id", "episode_num"),
    )
