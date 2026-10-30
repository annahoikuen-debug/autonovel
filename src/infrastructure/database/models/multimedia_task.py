from __future__ import annotations

"""マルチメディアタスクモデル定義。

Multimedia 系の非同期タスク状態。
"""

from sqlalchemy import Column, Integer, String, Text, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class MultimediaTask(Base):
    __tablename__ = "multimedia_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), nullable=False, unique=True)
    asset_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, server_default="pending")
    started_at = Column(CompatibleDateTime, server_default=func.now(), nullable=False)
    finished_at = Column(CompatibleDateTime, nullable=True)
    error = Column(Text, nullable=True)

    __table_args__ = (Index("ix_multimedia_tasks_task_id", "task_id"),)
