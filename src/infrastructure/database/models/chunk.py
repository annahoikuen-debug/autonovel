"""章チャンク・ベクトル表現データモデル (ORM)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base

import json

try:
    from pgvector.sqlalchemy import Vector as PGVector

    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    PGVector = None


class Vector(TypeDecorator):
    """PostgreSQL pgvector と SQLite JSON の透過的なハイブリッド型デコレータ"""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1536, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql" and HAS_PGVECTOR and PGVector is not None:
            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return list(value)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None or value == "null":
            return None
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if parsed is not None else None
            except Exception:
                return value
        return value


class ChapterChunk(Base):
    """小説本文の段落・シーンチャンクおよびベクトル埋め込みモデル."""

    __tablename__ = "chapter_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chapter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)
    chunk_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ChapterChunk(id={self.id}, chapter_id={self.chapter_id}, index={self.chunk_index})>"
