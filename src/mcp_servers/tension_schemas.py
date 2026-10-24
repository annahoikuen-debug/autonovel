"""Tension and Emotion Schemas for Real-time Measurement and Curve Control."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TensionScore(BaseModel):
    """感情およびテンション測定結果"""

    tension_score: float = Field(..., description="0.0 to 100.0")
    polarity: float = Field(..., description="-1.0 (negative) to +1.0 (positive)")
    dominant_emotion: str = Field(..., description="tension, joy, sorrow, anger, calm")
    feedback: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SegmentTension(BaseModel):
    """エピソード内の局所セグメントテンション"""

    segment_index: int
    segment_label: str  # 序盤, 展開, クライマックス, 結末
    char_count: int = 0
    tension_score: float = 0.0
    polarity: float = 0.0
    dominant_emotion: str = "calm"
    target_tension: Optional[float] = None
    snippet: str = ""


class TargetCurveTemplate(BaseModel):
    """エピソードの目標感情曲線テンプレート"""

    curve_type: str
    description: str
    target_points: List[float]  # e.g. [30.0, 55.0, 85.0, 40.0]
    stage_instructions: List[str]
    prompt_directive: str = ""


class CurveAnalysisResult(BaseModel):
    """本文の感情曲線分析・目標乖離評価結果"""

    curve_type: str
    overall_avg_tension: float
    segments: List[SegmentTension] = Field(default_factory=list)
    curve_fit_score: float = Field(..., description="目標曲線との一致度 (0.0〜1.0)")
    flatness_detected: bool = Field(default=False, description="起伏不足・中だるみの検知")
    peak_segment_index: int = 0
    actionable_guidance: List[str] = Field(default_factory=list)
    summary: str = ""


# 緊迫度・感情キーワード辞書
TENSION_KEYWORDS = {
    "high_tension": [
        "走る",
        "叫ぶ",
        "剣",
        "血",
        "逃げる",
        "迫る",
        "絶望",
        "閃光",
        "怒り",
        "衝突",
        "戦い",
        "交錯",
        "激痛",
        "轟音",
        "殺気",
        "刃",
        "run",
        "sword",
        "blood",
        "danger",
        "climax",
        "crisis",
    ],
    "relief_catharsis": [
        "安堵",
        "息を吐く",
        "微笑",
        "勝利",
        "静寂",
        "救われた",
        "光が満ちる",
        "温もり",
        "平穏",
        "肩の力を抜く",
        "解き放たれる",
    ],
    "positive": [
        "笑う",
        "光",
        "希望",
        "温かい",
        "勝利",
        "成功",
        "喜び",
        "smile",
        "hope",
        "victory",
    ],
    "negative": [
        "闇",
        "冷たい",
        "涙",
        "絶望",
        "敗北",
        "苦悶",
        "悲鳴",
        "dark",
        "tears",
        "despair",
    ],
}

# 定番の感情曲線プリセット
CURVE_PRESETS: Dict[str, Dict[str, Any]] = {
    "climax_catharsis": {
        "description": "王道の山場・カタルシス型（起:導入 -> 承:緊迫上昇 -> 転:激突・ピーク -> 結:勝利・安堵）",
        "target_points": [30.0, 60.0, 90.0, 45.0],
        "stage_instructions": [
            "【第1幕・導入】日常または不穏な予兆。抑制されたトーンで状況を提示する。",
            "【第2幕・展開】事態が急転・障害が発生。主人公の焦燥と緊張を高める。",
            "【第3幕・頂点】最大の危機または決戦。息詰まる攻防と感情の爆発を描く。",
            "【第4幕・余韻】決着と安堵。カタルシスと次への余韻（または引き）を残す。",
        ],
    },
    "cliffhanger": {
        "description": "引き・クリフハンガー型（終盤に向けて緊張を急上昇させ、絶頂で次話へ引く）",
        "target_points": [35.0, 50.0, 75.0, 95.0],
        "stage_instructions": [
            "【第1幕】状況の整理と伏線の仕込み。",
            "【第2幕】小さな異変が連鎖し始める。",
            "【第3幕】予想外の黒幕や新事実が発覚。",
            "【第4幕】衝撃の展開・絶体絶命の瞬間で『次話へ続く』とする。",
        ],
    },
    "rollercoaster": {
        "description": "ジェットコースター型（乱高下する緊張感で読者を飽きさせない）",
        "target_points": [40.0, 80.0, 45.0, 85.0],
        "stage_instructions": [
            "【第1幕】掴みの出来事・不穏な遭遇。",
            "【第2幕】一気にピンチへ突入。",
            "【第3幕】一時的な偽りの平穏・安堵。",
            "【第4幕】更なる真の試練・大波乱が襲う。",
        ],
    },
    "daily_rest": {
        "description": "日常・幕間型（緊張を低く抑え、キャラクターの掛け合いと精神的平穏を描く）",
        "target_points": [25.0, 35.0, 30.0, 20.0],
        "stage_instructions": [
            "【第1幕】穏やかな日常の始まり。",
            "【第2幕】クスッと笑える小さなハプニング。",
            "【第3幕】キャラ同士の絆の深まりや本音の対話。",
            "【第4幕】心温まる結末と明日への期待。",
        ],
    },
}
