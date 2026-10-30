from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, func

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""Outbox ORM モデル定義。

イベントアウトボックス（非同期メッセージ送信用キュー）を永続化する。
"""


class Outbox(Base):
    __tablename__ = "outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(CompatibleDateTime, server_default=func.now())
    processed_at = Column(CompatibleDateTime, nullable=True)
