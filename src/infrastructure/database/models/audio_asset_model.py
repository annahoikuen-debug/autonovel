from __future__ import annotations

from datetime import datetime

"""オーディオアセットモデル定義。"""

from sqlalchemy import DateTime, ForeignKey, Float, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base


class AudioAssetModel(Base):
    __tablename__ = "audio_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_num: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_audio_assets_book_ep", "book_id", "episode_num"),)
