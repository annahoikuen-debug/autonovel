"""ブランチプレイセッション ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `BranchPlaySession` を
`src/infrastructure/database/models/branch_play_session.py` へ実体移動。
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    String,
    func,
    text,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class BranchPlaySession(Base):
    """IF ルート分岐のプレイヤーセッション状態の ORM モデル。"""

    __tablename__ = "branch_play_sessions"

    id = Column(String(36), primary_key=True)
    book_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    current_node_id = Column(String(255), nullable=True)
    context_json = Column(CompatibleJSON, nullable=True)
    save_points_json = Column(CompatibleJSON, nullable=True)
    status = Column(String(20), nullable=True, server_default=text("'active'"))
    version = Column(Integer, nullable=False, server_default=text("1"))
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(CompatibleDateTime, server_default=func.now())
