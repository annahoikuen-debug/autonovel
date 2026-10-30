from __future__ import annotations

from datetime import datetime

"""出版スケジュールモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from src.infrastructure.database.models.base_orm import Base


class PublicationScheduleModel(Base):
    __tablename__ = "publication_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)  # "narou", "kakuyomu", "kindle", "kobo"
    episode_range_start = Column(Integer, nullable=False, default=1)
    episode_range_end = Column(Integer, nullable=False, default=1)
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, running, completed, failed, cancelled
    post_id = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
