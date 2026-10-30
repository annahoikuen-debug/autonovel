"""Book ORM モデル（infrastructure 層）。

TRACK-A4/A5: `src/backend/database/models.py` から `Book` を
`src/infrastructure/database/models/` へ実体移動する第一歩。
`book_mapper.py` はこちらから import する。
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class Book(Base):
    """書籍（小説）の ORM モデル。"""

    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    owner = relationship("User", back_populates="books")
    title = Column(String(200), nullable=False)
    genre = Column(String(100), default="")
    concept = Column(Text, default="")
    synopsis = Column(Text, default="")
    catchcopy = Column(String(255), default="")
    target_eps = Column(Integer, default=50)
    style_dna = Column(Text, default="")
    status = Column(String(50), default="draft")
    mode = Column(String(20), default="easy", nullable=False)
    created_at = Column(CompatibleDateTime, server_default=func.now())
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())
    marketing_data = Column(Text, default="")
    cumulative_tension = Column(Integer, default=0)
    cumulative_qol = Column(Integer, default=0)
    cumulative_cost = Column(Float, default=0.0)
    sanctuary_integrity = Column(Integer, default=100)
    current_branch_id = Column(Integer, nullable=True)
    # 楽観ロック用バージョン (``BranchPlaySession.version`` と同じ方式)
    version = Column(Integer, nullable=False, server_default=text("1"), default=1)
    ai_assistant_config = Column(
        CompatibleJSON,
        nullable=False,
        default={
            "enabled": False,
            "auto_suggest": False,
            "trigger_mode": "manual",
            "features": {"continue": True, "describe": True, "rewrite": True},
        },
    )
