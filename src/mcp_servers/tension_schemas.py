"""Tension and Emotion Schemas for Real-time Measurement."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class TensionScore:
    """感情およびテンション測定結果"""
    tension_score: float  # 0.0 to 100.0
    polarity: float       # -1.0 (negative) to +1.0 (positive)
    dominant_emotion: str # e.g., tension, joy, sorrow, anger, calm
    feedback: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# 緊迫度・感情キーワード辞書
TENSION_KEYWORDS = {
    "high_tension": ["走る", "叫ぶ", "剣", "血", "逃げる", "迫る", "絶望", "閃光", "怒り", "衝突", "戦い", "交錯", "run", "sword", "blood", "danger", "climax"],
    "positive": ["笑う", "光", "希望", "温かい", "勝利", "成功", "smile", "hope", "victory"],
    "negative": ["闇", "冷たい", "涙", "絶望", "敗北", "dark", "tears", "despair"],
}

