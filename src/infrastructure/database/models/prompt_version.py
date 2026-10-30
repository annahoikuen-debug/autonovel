from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""PromptVersion ORM モデル定義。

プロンプトのバージョン情報を永続化する。
"""


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=True)
    prompt_key = Column(String(100), nullable=False)
    version_tag = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    score_before = Column(Float)
    score_after = Column(Float)
    ab_test_metrics = Column(Text, default="{}")
    rollback_reason = Column(String(255))
    is_active = Column(Boolean, default=False)
    created_at = Column(CompatibleDateTime, server_default=func.now())
