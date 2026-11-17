"""ユーザー ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `User` を
`src/infrastructure/database/models/user.py` へ実体移動。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class User(Base):
    """ユーザーアカウントの ORM モデル。"""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("credits >= 0", name="chk_user_credits_non_negative"),)  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    def __contains__(self, item):
        # Allow checking for 'user_id', 'id', 'sub' as if they were keys
        if item in ("user_id", "id", "sub"):
            return True
        return hasattr(self, item)

    books = relationship("Book", back_populates="owner", cascade="all, delete-orphan")
