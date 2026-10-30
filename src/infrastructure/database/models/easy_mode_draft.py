from __future__ import annotations

"""イージモードドラフトモデル定義。

Gacha Pitch で生成した企画と、Quick Digest で生成した中間成果物を永続化する。

``kind`` 区分:
- ``gacha``: GachaService.generate_plans() の出力（3 案企画）
- ``digest``: DigestService.generate_digest() の出力（第 1 話＋あらすじ等）
- ``review_session``: ブラインドピアレビューセッション（複数ラウンド管理）

``parent_draft_id``:
- ``gacha``  Draft からは未設定
- ``digest`` Draft からは対応する ``gacha`` Draft の ``draft_id`` を参照
- ``review_session`` からは対応する ``gacha`` Draft の ``draft_id`` を参照
"""

from sqlalchemy import Column, Integer, String, Text, func, Index
from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class EasyModeDraft(Base):
    __tablename__ = "easy_mode_drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    draft_id = Column(String(64), unique=True, nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    review_session_json = Column(Text, nullable=True)  # ReviewSession シリアライズ用
    parent_draft_id = Column(String(64), nullable=True, index=True)
    book_id = Column(String(64), nullable=True, index=True)
    created_at = Column(CompatibleDateTime, server_default=func.now())
    updated_at = Column(CompatibleDateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_easy_mode_drafts_kind", "kind"),
        Index("idx_easy_mode_drafts_created", "created_at"),
    )
