from __future__ import annotations

"""3 系統判定パネル (M3: 検証平面)。

本番ゲートは変更せず、Validation Plane 専用の判定パネル。
3 系統の LLM judge を用い、以下のバイアス対策を行う：

- マスキング: プロンプトにモデル名・出力元の痕跡を含めない
- 自己偏好除外: 出力原稿のモデル family と同一の judge はその判定から除外
- 順序スワップ: ペアワイズ比較で (A,B) と (B,A) の両方を評価
- z 正規化 + 中央値投票: ScoreCalibrator による校正後、中央値を採用
- fail-closed: 全 judge 失敗時は PanelUnavailable を送出
"""

import asyncio
import json
import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Literal

from src.llm.resilient_gateway import ResilientLLMGateway
from src.services.score_calibrator import ScoreCalibrator

logger = logging.getLogger(__name__)

JudgeFamily = Literal["gemini", "anthropic", "openai", "other"]
JudgeVerdict = Literal["A", "B", "tie"]


class PanelUnavailable(RuntimeError):
    """全 judge が失敗し、パネル判定が不可能な場合。"""


@dataclass
class JudgeSpec:
    """単一の判定器仕様。"""

    family: JudgeFamily
    model: str
    purpose: str = "audit"
    weight: float = 1.0


@dataclass
class JudgeScore:
    """単一 judge の評価スコア。"""

    judge_id: str
    family: JudgeFamily
    model: str
    axis: str
    raw_score: float
    calibrated_score: float
    confidence: float = 1.0
    available: bool = True
    error: str | None = None


@dataclass
class PanelScore:
    """パネルによる軸別評価スコア。"""

    axis: str
    median_score: float
    scores: list[JudgeScore] = field(default_factory=list)
    n_available: int = 0
    n_excluded: int = 0


@dataclass
class PairwiseVerdict:
    """ペアワイズ比較の結果。"""

    winner: JudgeVerdict
    axis: str
    judge_verdicts: list[dict[str, Any]] = field(default_factory=list)
    agreement_rate: float = 0.0


class JudgePanel:
    """3 系統判定パネル。Validation Plane 専用。"""

    def __init__(
        self,
        judges: list[JudgeSpec],
        gateway: ResilientLLMGateway,
        calibrator: ScoreCalibrator | None = None,
        *,
        rho_threshold: float = 0.8,
        invariance_threshold: float = 3.0,
        retest_threshold: float = 5.0,
    ) -> None:
        self.judges = list(judges)
        self.gateway = gateway
        self.calibrator = calibrator or ScoreCalibrator()
        self.rho_threshold = rho_threshold
        self.invariance_threshold = invariance_threshold
        self.retest_threshold = retest_threshold

    # ------------------------------------------------------------------
    # プロンプト構築 (マスキング)
    # ------------------------------------------------------------------
    def _build_judge_prompt(
        self,
        text: str,
        axis: str,
        *,
        provenance_family: JudgeFamily | None = None,
    ) -> str:
        """判定器へのプロンプトを構築する（マスキング付き）。

        モデル名・family・出力元の痕跡を含めず、テキストと評価軸のみを渡す。
        """
        axis_descriptions = {
            "hook": "読者引き込み度（クリフハンガー・フックの強度）",
            "emotional": "感情曲線の自然さ・カタルシス",
            "character_consistency": "キャラクター言動の一貫性",
            "overall": "総合エンターテインメント性・品質",
        }
        axis_desc = axis_descriptions.get(axis, axis)

        # マスキング: model_name / family をプロンプトに含めない
        prompt = (
            "あなたは Web 小説の敏腕編集者です。以下の本文を読み、"
            f"「{axis_desc}」を 0-100 の整数で評価してください。\n"
            "出力は JSON のみで、キーは以下の通りです。\n"
            f'  "{axis}": スコア (0-100 の整数)\n'
            '  "critique": 70 字以内の講評\n'
            "\n---\n本文:\n"
            f"{text}\n---\n"
        )
        return prompt

    def _extract_score(self, response: str, axis: str) -> float | None:
        """LLM 応答から軸別スコアを抽出する。"""
        try:
            data = json.loads(response)
            val = data.get(axis)
            if val is None:
                return None
            score = float(val)
            return max(0.0, min(100.0, score))
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            return None

    def _should_exclude_judge(
        self, spec: JudgeSpec, provenance_family: JudgeFamily | None
    ) -> bool:
        """自己偏好除外: 同一 family の judge はその対象から除外する。"""
        if provenance_family is None:
            return False
        return spec.family == provenance_family

    async def _call_judge(
        self,
        spec: JudgeSpec,
        text: str,
        axis: str,
        *,
        provenance_family: JudgeFamily | None = None,
    ) -> JudgeScore:
        """単一 judge でスコアを取得する。"""
        judge_id = f"{spec.family}:{spec.model}"

        if self._should_exclude_judge(spec, provenance_family):
            return JudgeScore(
                judge_id=judge_id,
                family=spec.family,
                model=spec.model,
                axis=axis,
                raw_score=0.0,
                calibrated_score=0.0,
                confidence=0.0,
                available=False,
                error="excluded: same family as provenance",
            )

        try:
            prompt = self._build_judge_prompt(
                text, axis, provenance_family=provenance_family
            )
            response = await self.gateway.generate_text(
                prompt=prompt,
                primary_provider=spec.family,
                system_instruction=None,
                temperature=0.2,
            )
            response_text = str(response)
            raw_score = self._extract_score(response_text, axis)

            if raw_score is None:
                return JudgeScore(
                    judge_id=judge_id,
                    family=spec.family,
                    model=spec.model,
                    axis=axis,
                    raw_score=0.0,
                    calibrated_score=0.0,
                    confidence=0.0,
                    available=False,
                    error=f"score extraction failed for axis '{axis}'",
                )

            calibrated_score, _meta = self.calibrator.calibrate_single(
                specialist_name=spec.family,
                raw_score=raw_score,
                confidence=1.0,
                genre="general",
            )

            return JudgeScore(
                judge_id=judge_id,
                family=spec.family,
                model=spec.model,
                axis=axis,
                raw_score=raw_score,
                calibrated_score=calibrated_score,
                confidence=1.0,
                available=True,
                error=None,
            )
        except Exception as e:  # noqa: BLE001 - judge 個別の失敗は記録して続行
            logger.warning("Judge %s failed for axis %s: %r", judge_id, axis, e)
            return JudgeScore(
                judge_id=judge_id,
                family=spec.family,
                model=spec.model,
                axis=axis,
                raw_score=0.0,
                calibrated_score=0.0,
                confidence=0.0,
                available=False,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # 軸別スコア (z正規化 + 中央値)
    # ------------------------------------------------------------------
    async def score_axis(
        self,
        text: str,
        axis: str,
        *,
        provenance_family: JudgeFamily | None = None,
    ) -> PanelScore:
        """軸別スコアをパネルで評価する。

        各 judge で評価 → ScoreCalibrator で z 正規化 → 中央値を採用。
        自己偏好除外により、同一 family の judge は参加しない。
        """
        tasks = [
            self._call_judge(spec, text, axis, provenance_family=provenance_family)
            for spec in self.judges
        ]
        scores = await asyncio.gather(*tasks)

        available_scores = [s for s in scores if s.available]
        n_excluded = sum(1 for s in scores if not s.available and s.error and "excluded" in s.error)
        n_failed = sum(1 for s in scores if not s.available and "excluded" not in (s.error or ""))

        if not available_scores:
            raise PanelUnavailable(
                f"すべての judge が利用不可 (n_excluded={n_excluded}, n_failed={n_failed})"
            )

        calibrated = [s.calibrated_score for s in available_scores]
        median_score = statistics.median(calibrated)

        return PanelScore(
            axis=axis,
            median_score=round(median_score, 1),
            scores=available_scores,
            n_available=len(available_scores),
            n_excluded=n_excluded,
        )

    # ------------------------------------------------------------------
    # ペアワイズ比較 (順序スワップ付き)
    # ------------------------------------------------------------------
    def _build_pairwise_prompt(
        self,
        a: str,
        b: str,
        axis: str,
    ) -> str:
        """ペアワイズ比較用プロンプト（マスキング）。"""
        axis_descriptions = {
            "hook": "読者引き込み度",
            "emotional": "感情曲線の自然さ",
            "character_consistency": "キャラクター一貫性",
            "overall": "総合品質",
        }
        axis_desc = axis_descriptions.get(axis, axis)

        prompt = (
            "あなたは Web 小説の敏腕編集者です。以下の 2 つの本文 (A, B) を読み、"
            f"「{axis_desc}」の観点でどちらが優れているか比較してください。\n"
            "出力は JSON のみで、キーは以下の通りです。\n"
            '  "winner": "A" または "B" または "tie"\n'
            '  "critique": 70 字以内の比較理由\n'
            "\n---\nA:\n"
            f"{a}\n---\nB:\n"
            f"{b}\n---\n"
        )
        return prompt

    def _extract_verdict(self, response: str) -> JudgeVerdict | None:
        """LLM 応答から勝者を抽出する。"""
        try:
            data = json.loads(response)
            winner = data.get("winner")
            if winner in ("A", "B", "tie"):
                return winner
            return None
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            return None

    async def pairwise(
        self,
        a: str,
        b: str,
        axis: str = "overall",
        *,
        provenance_family: JudgeFamily | None = None,
    ) -> PairwiseVerdict:
        """ペアワイズ比較（順序スワップ付き）。

        (A, B) と (B, A) の両方を評価し、一致しなければ tie とする。
        これにより位置バイアスを軽減する。
        """
        judge_verdicts: list[dict[str, Any]] = []

        for spec in self.judges:
            if self._should_exclude_judge(spec, provenance_family):
                judge_verdicts.append({
                    "judge_id": f"{spec.family}:{spec.model}",
                    "family": spec.family,
                    "verdict": "excluded",
                    "reason": "same family as provenance",
                })
                continue

            judge_id = f"{spec.family}:{spec.model}"
            try:
                # 順序1: (A, B)
                prompt_ab = self._build_pairwise_prompt(a, b, axis)
                resp_ab = await self.gateway.generate_text(
                    prompt=prompt_ab,
                    primary_provider=spec.family,
                    system_instruction=None,
                    temperature=0.2,
                )
                verdict_ab = self._extract_verdict(str(resp_ab))

                # 順序2: (B, A)
                prompt_ba = self._build_pairwise_prompt(b, a, axis)
                resp_ba = await self.gateway.generate_text(
                    prompt=prompt_ba,
                    primary_provider=spec.family,
                    system_instruction=None,
                    temperature=0.2,
                )
                verdict_ba = self._extract_verdict(str(resp_ba))

                # 位置バイアス対策: 両方で一致する勝者のみ採用
                if verdict_ab == verdict_ba and verdict_ab is not None:
                    final_verdict: JudgeVerdict = verdict_ab
                else:
                    final_verdict = "tie"

                judge_verdicts.append({
                    "judge_id": judge_id,
                    "family": spec.family,
                    "verdict_ab": verdict_ab,
                    "verdict_ba": verdict_ba,
                    "final_verdict": final_verdict,
                })
            except Exception as e:  # noqa: BLE001
                logger.warning("Pairwise judge %s failed: %r", judge_id, e)
                judge_verdicts.append({
                    "judge_id": judge_id,
                    "family": spec.family,
                    "verdict": "error",
                    "reason": str(e),
                })

        # 多数決で最終勝者を決定
        valid_verdicts = [
            v["final_verdict"]
            for v in judge_verdicts
            if v.get("final_verdict") in ("A", "B", "tie")
        ]
        if not valid_verdicts:
            raise PanelUnavailable("すべての judge がペアワイズ比較に失敗しました")

        counts: dict[JudgeVerdict, int] = {"A": 0, "B": 0, "tie": 0}
        for v in valid_verdicts:
            counts[v] += 1  # type: ignore[assignment]

        winner: JudgeVerdict = max(counts, key=counts.get)  # type: ignore[assignment]
        # 同点の場合は tie
        max_count = counts[winner]
        tied_winners = [k for k, v in counts.items() if v == max_count]
        if len(tied_winners) > 1:
            winner = "tie"

        agreement_rate = (
            sum(1 for v in valid_verdicts if v == winner) / len(valid_verdicts)
            if valid_verdicts
            else 0.0
        )

        return PairwiseVerdict(
            winner=winner,
            axis=axis,
            judge_verdicts=judge_verdicts,
            agreement_rate=round(agreement_rate, 3),
        )


__all__ = [
    "JudgePanel",
    "JudgeSpec",
    "JudgeScore",
    "PanelScore",
    "PairwiseVerdict",
    "PanelUnavailable",
    "JudgeFamily",
    "JudgeVerdict",
]
