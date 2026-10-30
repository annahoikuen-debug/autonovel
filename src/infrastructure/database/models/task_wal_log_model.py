from __future__ import annotations

"""タスク WAL ログモデル定義。"""

from sqlalchemy import Column, Integer, String, Text, DateTime, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class TaskWALLogModel(Base):
    __tablename__ = "task_wal_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), nullable=False, index=True)
    dag_id = Column(String(64), nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    state = Column(String(20), nullable=False)
    input_json = Column(Text, nullable=True)
    output_json = Column(Text, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_task_wal_logs_dag_id", "dag_id"),
        Index("idx_task_wal_logs_node_id", "node_id"),
        Index("idx_task_wal_logs_task_id", "task_id"),
        Index("idx_task_wal_logs_heartbeat", "heartbeat_at"),
    )
