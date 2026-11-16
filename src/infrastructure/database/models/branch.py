"""ブランチ ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `Branch` を
`src/infrastructure/database/models/branch.py` へ実体移動。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class Branch(Base):
    """小説の分岐（ブランチ）の ORM モデル。"""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fork_ep_num: Mapped[int] = mapped_column(Integer, default=0)
    graph_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
