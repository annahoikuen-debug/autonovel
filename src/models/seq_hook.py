"""
改善案1・2 用モデル：序盤フック採点結果・CTR採点結果。

フラグ ENABLE_SEQ_HOOK_WIRING / ENABLE_CTR_WIRING が既定 OFF の間は、
現行の GenerationResponse スキーマに Optional フィールドとして追加され、
バイト同一契約を維持する。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HookMetrics(BaseModel):
    """序盤フック・章末引きの採点結果（改善案1）。"""

    ep_num: int = Field(..., ge=1, le=3, description="対象エピソード番号（1〜3話）")
    hook_type: str = Field(..., description="crisis / shocking_truth / triumph_trigger / peaceful")
    score: float = Field(..., ge=0.0, le=100.0, description="フックスコア（0〜100点）")
    requires_rewrite: bool = Field(..., description="章末引きのリライトが必要か")
    reason: str = Field(..., description="採点理由・リライト指令")
    tail_sentence: str = Field(..., description="末尾の文章")


class CTRMetrics(BaseModel):
    """タイトル・キャッチコピーのCTR採点結果（改善案2）。"""

    title_score: float = Field(..., ge=0.0, le=100.0, description="タイトルCTRスコア（0〜100点）")
    catchphrase_score: float = Field(..., ge=0.0, le=100.0, description="キャッチコピーCTRスコア（0〜100点）")
    title_needs_improvement: bool = Field(..., description="タイトルの改善が必要か")
    catchphrase_needs_improvement: bool = Field(..., description="キャッチコピーの改善が必要か")
    syntax_type: str = Field(..., description="トレンド構文タイプ（追放ざまぁ / 勘違い無双 / 無自覚無双 / 一般）")


__all__ = ["HookMetrics", "CTRMetrics"]
