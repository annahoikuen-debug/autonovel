"""Book ORM モデル（infrastructure 層）。

TRACK-A4/A5: `src/backend/database/models.py` から `Book` を
`src/infrastructure/database/models/` へ実体移動する第一歩。
`book_mapper.py` はこちらから import する。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class Book(Base):
    """書籍（小説）の ORM モデル。"""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True, index=True
    )
    owner = relationship("User", back_populates="books")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="")
    concept: Mapped[str] = mapped_column(Text, default="")
    synopsis: Mapped[str] = mapped_column(Text, default="")
    catchcopy: Mapped[str] = mapped_column(String(255), default="")
    target_eps: Mapped[int] = mapped_column(Integer, default=50)
    style_dna: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    mode: Mapped[str] = mapped_column(String(20), default="easy", nullable=False)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        CompatibleDateTime, server_default=func.now(), onupdate=func.now()
    )
    marketing_data: Mapped[str] = mapped_column(Text, default="")
    cumulative_tension: Mapped[int] = mapped_column(Integer, default=0)
    cumulative_qol: Mapped[int] = mapped_column(Integer, default=0)
    cumulative_cost: Mapped[float] = mapped_column(Float, default=0.0)
    sanctuary_integrity: Mapped[int] = mapped_column(Integer, default=100)
    current_branch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 楽観ロック用バージョン (``BranchPlaySession.version`` と同じ方式)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"), default=1)
    ai_assistant_config: Mapped[dict] = mapped_column(
        CompatibleJSON,
        nullable=False,
        default={
            "enabled": False,
            "auto_suggest": False,
            "trigger_mode": "manual",
            "features": {"continue": True, "describe": True, "rewrite": True},
        },
    )
