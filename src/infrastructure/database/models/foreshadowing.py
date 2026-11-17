from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""Foreshadowing ORM モデル定義。

伏線情報を永続化する。
"""


class Foreshadowing(Base):
    __tablename__ = "foreshadowing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ep_num: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(100))
    payoff_ep: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payoff_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    strength: Mapped[float] = mapped_column(Float, default=1.0)
    fulfilled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint("book_id", "branch_id", "ep_num", "type", name="uq_foreshadowing"),
    )
