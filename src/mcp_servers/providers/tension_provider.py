"""Tension Analyzer Provider for Real-time Emotion and Tension Measurement."""
from __future__ import annotations

from typing import Optional
from src.mcp_servers.tension_schemas import TensionScore, TENSION_KEYWORDS


class TensionAnalyzer:
    """シーンテキストの感情極性および緊張度（テンション）を計測・分析するプロバイダー"""

    def calculate_polarity(self, text: str) -> float:
        """テキストのポジティブ・ネガティブ極性(-1.0 〜 +1.0)を算出する"""
        pos_count = sum(1 for word in TENSION_KEYWORDS["positive"] if word in text)
        neg_count = sum(1 for word in TENSION_KEYWORDS["negative"] if word in text)
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        return float(pos_count - neg_count) / total

    def calculate_tension(self, text: str, target_tension: Optional[float] = None) -> TensionScore:
        """テキストから緊張度スコア(0〜100)、極性、主要感情を算出する"""
        if not text:
            return TensionScore(tension_score=0.0, polarity=0.0, dominant_emotion="calm", feedback="Text is empty.")

        # 緊迫キーワードの出現密度を計算
        high_tension_hits = sum(text.count(word) for word in TENSION_KEYWORDS["high_tension"])
        exclamation_count = text.count("!") + text.count("！")

        # 簡易スコア算出式
        base_score = float(high_tension_hits * 15.0 + exclamation_count * 5.0)
        # 文字数に応じた補正
        length_factor = min(max(len(text) / 50.0, 0.5), 2.0)
        tension_score = min(max(base_score / length_factor, 10.0), 100.0)

        # 特殊キーワード判定でスコア下駄履かせ (例: 危機ワードが多い場合)
        if high_tension_hits >= 3:
            tension_score = max(tension_score, 75.0)

        polarity = self.calculate_polarity(text)

        # 主要感情の決定
        if tension_score >= 70.0:
            dominant_emotion = "tension"
        elif polarity > 0.2:
            dominant_emotion = "joy"
        elif polarity < -0.2:
            dominant_emotion = "sorrow"
        else:
            dominant_emotion = "calm"

        # フィードバック生成
        feedback = f"Analyzed successfully. Tension is {tension_score:.1f}."
        if target_tension is not None and tension_score < target_tension:
            feedback += f" Warning: Tension is below target ({target_tension}). Consider adding more action, dramatic conflict, or pacing."

        return TensionScore(
            tension_score=tension_score,
            polarity=polarity,
            dominant_emotion=dominant_emotion,
            feedback=feedback,
        )
