from __future__ import annotations

from datetime import datetime

"""バックグラウンドタスクモデル定義。"""

from sqlalchemy import String, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class BackgroundTask(Base):
    __tablename__ = "background_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="")
    sub_message: Mapped[str] = mapped_column(String(500), default="")
    streaming_text: Mapped[str] = mapped_column(Text, default="")
    logs: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str | None] = mapped_column(Text)
    result_data: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        CompatibleDateTime, server_default=func.now(), onupdate=func.now()
    )
