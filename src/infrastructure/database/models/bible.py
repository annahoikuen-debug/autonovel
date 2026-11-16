"""バイブル（作品設定） ORM モデル (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `Bible` を
`src/infrastructure/database/models/bible.py` へ実体移動。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.models.safe_datetime import SafeDateTime


class Bible(Base):
    """作品の圣经（設定集）の ORM モデル。"""

    __tablename__ = "bibles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 作品単位の圣经参照が hot filter なので index を張る
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    settings: Mapped[str] = mapped_column(Text, default="")
    revealed: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(SafeDateTime, server_default=func.now())
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
