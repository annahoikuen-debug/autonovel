from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""タスク WAL ログモデル定義。"""


class TaskWALLogModel(Base):
    __tablename__ = "task_wal_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dag_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_task_wal_logs_worker_id", "worker_id"),
        Index("idx_task_wal_logs_dag_id", "dag_id"),
        Index("idx_task_wal_logs_node_id", "node_id"),
        Index("idx_task_wal_logs_task_id", "task_id"),
        Index("idx_task_wal_logs_heartbeat", "heartbeat_at"),
    )
