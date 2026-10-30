from __future__ import annotations

"""生成実行モデル定義。"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    chapter_ep = Column(Integer, nullable=True)
    task_type = Column(String(50), nullable=False, default="writing")
    prompt_version = Column(String(100), nullable=True)
    model_name = Column(String(100), nullable=True)
    params_json = Column(Text, nullable=True)
    input_hash = Column(String(64), nullable=True)
    output_preview = Column(Text, nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_generation_run_book_id", "book_id"),
        Index("idx_generation_run_chapter_ep", "chapter_ep"),
    )
