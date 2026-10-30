from __future__ import annotations

"""バックグラウンドタスクモデル定義。"""

from sqlalchemy import Column, String, Integer, Text, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class BackgroundTask(Base):
    __tablename__ = "background_tasks"

    id = Column(String(64), primary_key=True)
    status = Column(String(20), default="running")
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)
    message = Column(String(500), default="")
    sub_message = Column(String(500), default="")
    streaming_text = Column(Text, default="")
    logs = Column(Text, default="[]")
    error = Column(Text)
    result_data = Column(Text)
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())
