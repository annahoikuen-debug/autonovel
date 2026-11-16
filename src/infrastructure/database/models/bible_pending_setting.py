"""バイブル保留設定 ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `BiblePendingSetting` を
`src/infrastructure/database/models/bible_pending_setting.py` へ実体移動。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class BiblePendingSetting(Base):
    """バイブル設定の保留（承認待ち）項目の ORM モデル。"""

    __tablename__ = "bible_pending_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    proposed_value: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())
