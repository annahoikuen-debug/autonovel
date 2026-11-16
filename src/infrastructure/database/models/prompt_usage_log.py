from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base


"""PromptUsageLog ORM モデル定義。

プロンプト使用ログ（テンプレートごとのヒット数・応答時間等）を永続化する。
"""


class PromptUsageLog(Base):
    __tablename__ = "prompt_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)
    template_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_time_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_time_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_prompt_usage_timestamp", "timestamp"),
        Index("idx_prompt_usage_template", "template_name"),
    )
