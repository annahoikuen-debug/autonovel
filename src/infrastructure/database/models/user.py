"""ユーザー ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `User` を
`src/infrastructure/database/models/user.py` へ実体移動。
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class User(Base):
    """ユーザーアカウントの ORM モデル。"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("credits >= 0", name="chk_user_credits_non_negative"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    role = Column(String(20), default="user", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    plan_tier = Column(String(20), default="free", nullable=False)
    credits = Column(Integer, default=50, nullable=False)
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    def __contains__(self, item):
        # Allow checking for 'user_id', 'id', 'sub' as if they were keys
        if item in ("user_id", "id", "sub"):
            return True
        return hasattr(self, item)

    books = relationship("Book", back_populates="owner", cascade="all, delete-orphan")
