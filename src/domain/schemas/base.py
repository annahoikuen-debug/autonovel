from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class AutoNovelBaseSchema(BaseModel):
    """v5.0 ドメインモデル共通基底クラス"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="ignore",
    )

class TimestampedSchema(AutoNovelBaseSchema):
    # default_factory を使い、クラス定義時に評価されるのを防ぐ
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
