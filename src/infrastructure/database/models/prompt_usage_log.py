from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    func,
)

from src.infrastructure.database.models.base_orm import Base


"""PromptUsageLog ORM モデル定義。

プロンプト使用ログ（テンプレートごとのヒット数・応答時間等）を永続化する。
"""


class PromptUsageLog(Base):
    __tablename__ = "prompt_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    template_name = Column(String(255), nullable=False, index=True)
    hits = Column(Integer, nullable=False, default=0)
    total_time_ms = Column(Float, nullable=False, default=0.0)
    avg_time_ms = Column(Float, nullable=False, default=0.0)
    last_accessed = Column(DateTime, nullable=True)
    error_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_prompt_usage_timestamp", "timestamp"),
        Index("idx_prompt_usage_template", "template_name"),
    )
