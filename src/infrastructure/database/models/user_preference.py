"""ユーザー設定 ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `UserPreference` を
`src/infrastructure/database/models/user_preference.py` へ実体移動。
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime, CompatibleJSON


class UserPreference(Base):
    """ユーザー単位の AI アシスタント設定（オプトイン管理）の ORM モデル。"""

    __tablename__ = "user_preferences"

    user_id = Column(Integer, primary_key=True, nullable=False)
    easy_mode_ai_enabled = Column(Boolean, default=False, nullable=False)
    ai_features = Column(CompatibleJSON, nullable=False, default={})
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())
