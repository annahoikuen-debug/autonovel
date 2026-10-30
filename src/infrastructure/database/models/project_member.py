from __future__ import annotations

"""プロジェクトメンバーモデル定義。"""

from sqlalchemy import Column, Integer, String, ForeignKey, func
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    user_name = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False, default="viewer")
    created_at = Column(CompatibleDateTime, server_default=func.now())
