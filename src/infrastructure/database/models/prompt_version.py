from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""PromptVersion ORM モデル定義。

プロンプトのバージョン情報を永続化する。
"""


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=True)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score_before: Mapped[float | None] = mapped_column(Float)
    score_after: Mapped[float | None] = mapped_column(Float)
    ab_test_metrics: Mapped[str] = mapped_column(Text, default="{}")
    rollback_reason: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
