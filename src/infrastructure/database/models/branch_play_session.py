"""ブランチプレイセッション ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `BranchPlaySession` を
`src/infrastructure/database/models/branch_play_session.py` へ実体移動。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class BranchPlaySession(Base):
    """IF ルート分岐のプレイヤーセッション状態の ORM モデル。"""

    __tablename__ = "branch_play_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    book_id: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_node_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    save_points_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True, server_default=text("'active'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
