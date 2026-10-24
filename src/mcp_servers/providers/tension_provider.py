"""Tension Analyzer Provider for Real-time Emotion, Tension Measurement, and Arc Control."""

from __future__ import annotations

import math
from typing import List, Optional

from src.mcp_servers.tension_schemas import (
    CURVE_PRESETS,
    CurveAnalysisResult,
    SegmentTension,
    TargetCurveTemplate,
    TensionScore,
    TENSION_KEYWORDS,
)


class TensionAnalyzer:
    """シーンテキストの感情極性および緊張度（テンション）を計測・分析し、感情曲線を制御するプロバイダー"""

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
        relief_hits = sum(text.count(word) for word in TENSION_KEYWORDS["relief_catharsis"])
        exclamation_count = text.count("!") + text.count("！")
        ellipsis_count = text.count("…") + text.count("...")

        # 文長リズム分析（短い文が多いほど緊迫感が高い）
        sentences = [s.strip() for s in text.replace("\n", "。").split("。") if s.strip()]
        avg_sentence_len = sum(len(s) for s in sentences) / max(1, len(sentences))

        # 基本スコア計算
        # 緊迫キーワードや感嘆符があるときのみ短文ボーナスを適用
        if high_tension_hits >= 1 or exclamation_count >= 1:
            short_sentence_bonus = max(0.0, (40.0 - avg_sentence_len) * 0.8)
        else:
            short_sentence_bonus = 0.0
        base_score = float(
            high_tension_hits * 14.0 + exclamation_count * 4.0 + ellipsis_count * 2.0 + short_sentence_bonus
        )

        # カタルシス・緩和ワードによる緩和効果
        base_score = max(5.0, base_score - relief_hits * 6.0)

        # 文字数に応じた正規化ファクター
        length_factor = min(max(len(text) / 100.0, 0.6), 2.5)
        raw_tension = base_score / length_factor

        # 緊迫語が頻発している場合は下駄を履かせる
        if high_tension_hits >= 3:
            raw_tension = max(raw_tension, 70.0)
        elif high_tension_hits >= 1:
            raw_tension = max(raw_tension, 45.0)

        tension_score = min(max(raw_tension, 10.0), 100.0)
        polarity = self.calculate_polarity(text)

        # 主要感情の決定
        if tension_score >= 70.0:
            dominant_emotion = "tension"
        elif relief_hits >= 2 or polarity > 0.2:
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
            tension_score=round(tension_score, 1),
            polarity=round(polarity, 2),
            dominant_emotion=dominant_emotion,
            feedback=feedback,
        )

    def generate_target_curve(self, curve_type: str = "climax_catharsis") -> TargetCurveTemplate:
        """エピソード構成に合わせた目標感情曲線とディレクション指示を生成する"""
        preset = CURVE_PRESETS.get(curve_type, CURVE_PRESETS["climax_catharsis"])
        targets = preset["target_points"]
        stages = preset["stage_instructions"]

        # プロンプト用の整形テキストを作成
        directive_lines = [
            f"### 【本話の感情曲線・テンション設計（型: {curve_type}）】",
            f"概要: {preset['description']}",
            "執筆時は以下の4幕テンション目標に従い、緩急と起伏を明確に描いてください:",
        ]
        labels = ["序盤", "展開", "クライマックス", "結末"]
        for idx, (label, target, inst) in enumerate(zip(labels, targets, stages, strict=False)):
            directive_lines.append(f"- 第{idx + 1}幕（{label} / 目標緊張度: {target:.0f}）: {inst}")

        prompt_directive = "\n".join(directive_lines)

        return TargetCurveTemplate(
            curve_type=curve_type,
            description=preset["description"],
            target_points=targets,
            stage_instructions=stages,
            prompt_directive=prompt_directive,
        )

    def analyze_novel_arc(
        self,
        text: str,
        curve_type: str = "climax_catharsis",
        custom_targets: Optional[List[float]] = None,
    ) -> CurveAnalysisResult:
        """本文を4セグメントに分割し、感情曲線（テンション推移）と目標曲線の一致度・中だるみを分析する"""
        if not text or len(text.strip()) == 0:
            return CurveAnalysisResult(
                curve_type=curve_type,
                overall_avg_tension=0.0,
                segments=[],
                curve_fit_score=0.0,
                flatness_detected=True,
                actionable_guidance=["本文が空です。"],
                summary="分析対象のテキストが存在しません。",
            )

        preset = CURVE_PRESETS.get(curve_type, CURVE_PRESETS["climax_catharsis"])
        target_points = custom_targets or preset["target_points"]
        num_segments = len(target_points)

        # 4分割（文字数ベースで自然な句点区切りを探索）
        segments_text = self._split_into_segments(text, num_segments)
        labels = ["序盤", "展開", "クライマックス", "結末"]

        segment_results: List[SegmentTension] = []
        actual_scores: List[float] = []

        for idx, seg_text in enumerate(segments_text):
            score_res = self.calculate_tension(seg_text)
            label = labels[idx] if idx < len(labels) else f"第{idx + 1}区間"
            target_val = target_points[idx] if idx < len(target_points) else 50.0

            seg_model = SegmentTension(
                segment_index=idx,
                segment_label=label,
                char_count=len(seg_text),
                tension_score=score_res.tension_score,
                polarity=score_res.polarity,
                dominant_emotion=score_res.dominant_emotion,
                target_tension=target_val,
                snippet=seg_text[:80] + ("..." if len(seg_text) > 80 else ""),
            )
            segment_results.append(seg_model)
            actual_scores.append(score_res.tension_score)

        avg_tension = sum(actual_scores) / max(1, len(actual_scores))
        max_tension = max(actual_scores)
        min_tension = min(actual_scores)
        peak_idx = actual_scores.index(max_tension)

        # 起伏不足（中だるみ）の判定: 最大と最小の差が 18.0 未満なら起伏不足
        flatness = (max_tension - min_tension) < 18.0

        # 目標曲線との適合度（Curve Fit Score: 0.0〜1.0）
        # 平均二乗誤差 (MSE) を正規化してスコア化
        mse = sum((act - tgt) ** 2 for act, tgt in zip(actual_scores, target_points, strict=False)) / len(target_points)
        rmse = math.sqrt(mse)
        # RMSEが0なら1.0、55以上離れると0.0近辺
        fit_score = max(0.0, min(1.0, 1.0 - (rmse / 55.0)))

        # 具体的な改善ガイダンスの生成
        guidance: List[str] = []
        if flatness:
            guidance.append(
                "【起伏不足】全体を通してテンションの落差が少なく、中だるみしています。山場を一段引き上げるか、序盤のトーンを抑えて対比を作ってください。"
            )

        for idx, (act, tgt) in enumerate(zip(actual_scores, target_points, strict=False)):
            diff = act - tgt
            seg_name = segment_results[idx].segment_label
            if diff < -20.0:
                guidance.append(
                    f"【{seg_name}の緊迫度不足】目標({tgt:.0f})に対して実測({act:.0f})が大幅に不足しています。短い文での切迫感や緊迫語・衝突アクションを補強してください。"
                )
            elif diff > 25.0 and idx == len(actual_scores) - 1 and curve_type == "climax_catharsis":
                guidance.append(
                    f"【{seg_name}の余韻不足】結末のテンションが高すぎます。勝利の余韻や安堵、読後感のカタルシスを描いて緊張を緩和させてください。"
                )

        if not guidance:
            guidance.append("テンション曲線は目標アークと非常によく合致しています。素晴らしい抑揚と起伏です。")

        summary = f"感情曲線一致度: {fit_score * 100:.1f}%, 平均テンション: {avg_tension:.1f}, ピーク区間: {segment_results[peak_idx].segment_label}"

        return CurveAnalysisResult(
            curve_type=curve_type,
            overall_avg_tension=round(avg_tension, 1),
            segments=segment_results,
            curve_fit_score=round(fit_score, 3),
            flatness_detected=flatness,
            peak_segment_index=peak_idx,
            actionable_guidance=guidance,
            summary=summary,
        )

    def _split_into_segments(self, text: str, num_segments: int) -> List[str]:
        """テキストを段落・文境界を考慮して均等に num_segments 個に分割する"""
        if not text or num_segments <= 1:
            return [text]

        # 改行で分割された段落ブロックがある場合（段落数が num_segments と一致すれば優先）
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        if len(paragraphs) == num_segments:
            return paragraphs

        # 文単位（「。」）で分割
        sentences = [s.strip() + "。" for s in text.replace("\r\n", "\n").split("。") if s.strip()]
        if len(sentences) < num_segments:
            chunk_size = max(1, len(text) // num_segments)
            return [
                text[i * chunk_size : (i + 1) * chunk_size if i < num_segments - 1 else len(text)]
                for i in range(num_segments)
            ]

        total_sentences = len(sentences)
        k, m = divmod(total_sentences, num_segments)
        segments: List[str] = []
        start = 0
        for i in range(num_segments):
            end = start + k + (1 if i < m else 0)
            segments.append("".join(sentences[start:end]))
            start = end
        return segments
