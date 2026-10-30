"""バイブル保留設定 ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `BiblePendingSetting` を
`src/infrastructure/database/models/bible_pending_setting.py` へ実体移動。
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Float,
    Integer,
    String,
    Text,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class BiblePendingSetting(Base):
    """バイブル設定の保留（承認待ち）項目の ORM モデル。"""

    __tablename__ = "bible_pending_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(100), nullable=False)
    proposed_value = Column(Text, default="")
    confidence = Column(Float, default=0.0)
    status = Column(String(50), default="pending")
    created_at = Column(CompatibleDateTime, server_default=func.now())
