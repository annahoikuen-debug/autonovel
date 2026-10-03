"""挿絵生成 API の Pydantic スキーマ定義。

`/generate` と `/yonkoma` は従来 `request: dict[str, Any]` で生ボディを受けていたため、
Pydantic のバリデーション（型強制・未知フィールド拒否）が一切走らず、
`book_id` の欠落が `KeyError` -> 500 になっていた。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IllustrationGenerateRequest(BaseModel):
    """単一挿絵生成リクエスト (`POST /generate`)。"""

    # 未知フィールドを 422 で拒否する
    model_config = ConfigDict(extra="forbid")

    book_id: int = Field(..., ge=1, description="対象 Book ID")
    illustration_type: str = Field(..., min_length=1, description="挿絵種別 (scene/character/yonkoma 等)")
    episode_number: int | None = Field(default=None, ge=1, description="話数")
    model: str = Field("auto", description="生成モデル (fast/quality/ultra/auto)")
    enable_r15: bool = Field(default=False, description="R15 表現を許可するか")


class YonkomaGenerateRequest(BaseModel):
    """4コマ漫画生成リクエスト (`POST /yonkoma`)。"""

    model_config = ConfigDict(extra="forbid")

    book_id: int = Field(..., ge=1, description="対象 Book ID")
    episode_text: str = Field(default="", description="1話分の本文")
    panels: int = Field(default=6, ge=3, le=6, description="コマ数 (3〜6)")
    model: str = Field("auto", description="生成モデル (fast/quality/ultra/auto)")
    enable_r15: bool = Field(default=False, description="R15 表現を許可するか")
    episode_number: int | None = Field(default=None, ge=1, description="話数")
    book_context: dict[str, Any] = Field(default_factory=dict, description="作品の補助情報")
    yonkoma_enabled: bool = Field(True, description="画像生成を伴うか (False ならプロンプトのみ)")


__all__ = ["IllustrationGenerateRequest", "YonkomaGenerateRequest"]
