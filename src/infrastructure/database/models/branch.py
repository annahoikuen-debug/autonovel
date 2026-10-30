"""ブランチ ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `Branch` を
`src/infrastructure/database/models/branch.py` へ実体移動。
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class Branch(Base):
    """小説の分岐（ブランチ）の ORM モデル。"""

    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, nullable=True)
    fork_ep_num = Column(Integer, default=0)
    graph_json = Column(CompatibleJSON, nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())
