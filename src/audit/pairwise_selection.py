from __future__ import annotations

"""Best-of-N ペアワイズ選抜 (M5-A)。

複数の生成候補から、静的層フィルタ + ペアワイズ決勝で最適な1案を選ぶ。
既存の品質ゲートには触れず、ENABLE_PAIRWISE_SELECTION env フラグでオプトイン。
"""

import asyncio
import os
from dataclasses import dataclass

from src.audit.judge_panel import JudgePanel, PairwiseVerdict

# 候補生成時に静的層スコアを持つ想定
@dataclass
class GenerationCandidate:
    """生成候補。"""

    text: str
    static_score: float  # 静的ルール層のスコア (0-100)
    generation_index: int  # 生成順序 (0-based)


@dataclass
class SelectionResult:
    """選抜結果。"""

    selected_index: int
    selected_text: str
    selected_static_score: float
    pairwise_verdicts: list[PairwiseVerdict]
    method: str  # "static_only" | "pairwise" | "fallback_first"
    n_candidates: int


class PairwiseSelector:
    """Best-of-N ペアワイズ選抜器。"""

    def __init__(
        self,
        panel: JudgePanel,
        *,
        top_n_from_static: int = 2,
        provenance_family: str | None = None,
    ) -> None:
        self.panel = panel
        self.top_n_from_static = top_n_from_static
        self.provenance_family = provenance_family

    @staticmethod
    def is_enabled() -> bool:
        """ペアワイズ選抜が有効か (env ENABLE_PAIRWISE_SELECTION)。"""
        return is_pairwise_enabled() or os.environ.get(
            "ENABLE_PAIRWISE_SELECTION", "false"
        ).strip().lower() in ("true", "1", "yes", "on")

    def _rank_by_static(self, candidates: list[GenerationCandidate]) -> list[GenerationCandidate]:
        """静的スコアで上位 N 件を選ぶ。同点は生成順序で安定ソート。"""
        return sorted(
            candidates,
            key=lambda c: (-c.static_score, c.generation_index),
        )[: self.top_n_from_static]

    async def select(
        self,
        candidates: list[GenerationCandidate],
        axis: str = "overall",
    ) -> SelectionResult:
        """複数候補から最適な1案を選抜する。

        フロー:
          1. 静的層で上位 top_n_from_static 件を絞る
          2. 1件ならそのまま返す (static_only)
          3. 2件以上ならペアワイズ決勝 (順序スワップ付き)
          4. ペアワイズが失敗したら静的上位1件にフォールバック
        """
        if not candidates:
            raise ValueError("候補が空です")

        n_candidates = len(candidates)

        # 候補が1件のみならペアワイズ不要
        if n_candidates == 1:
            c = candidates[0]
            return SelectionResult(
                selected_index=c.generation_index,
                selected_text=c.text,
                selected_static_score=c.static_score,
                pairwise_verdicts=[],
                method="static_only",
                n_candidates=1,
            )

        # Step 1: 静的層で絞り込み
        top = self._rank_by_static(candidates)

        # Step 2: 絞り込み後1件ならそのまま
        if len(top) == 1:
            c = top[0]
            return SelectionResult(
                selected_index=c.generation_index,
                selected_text=c.text,
                selected_static_score=c.static_score,
                pairwise_verdicts=[],
                method="static_only",
                n_candidates=n_candidates,
            )

        # Step 3: ペアワイズ決勝 (top_n_from_static 件を総当たり or トーナメント)
        # ここではシンプルに「静的上位1位」と「静的上位2位」を比較。
        # 3件以上ある場合は、1位と2位、勝者と3位、と順に比較するトーナメント。
        finalists = top[:]
        verdicts: list[PairwiseVerdict] = []

        # トーナメント方式：現在のチャンピオンと次の挑戦者を比較
        champion = finalists[0]
        for challenger in finalists[1:]:
            try:
                verdict = await self.panel.pairwise(
                    champion.text,
                    challenger.text,
                    axis=axis,
                    provenance_family=self.provenance_family,
                )
                verdicts.append(verdict)
                if verdict.winner == "B":
                    # 挑戦者が勝ちならチャンピオン交代
                    champion = challenger
                elif verdict.winner == "tie":
                    # 引き分けは静的スコアで決着
                    if challenger.static_score > champion.static_score:
                        champion = challenger
                # "A" の場合はチャンピオン維持
            except Exception:  # noqa: BLE001 - ペアワイズ失敗時は静的スコアで維持
                if challenger.static_score > champion.static_score:
                    champion = challenger

        selected = champion
        method = "pairwise" if verdicts else "fallback_first"

        return SelectionResult(
            selected_index=selected.generation_index,
            selected_text=selected.text,
            selected_static_score=selected.static_score,
            pairwise_verdicts=verdicts,
            method=method,
            n_candidates=n_candidates,
        )


async def select_best_of_n(
    candidates: list[GenerationCandidate],
    panel: JudgePanel,
    axis: str = "overall",
    provenance_family: str | None = None,
) -> SelectionResult:
    """Best-of-N 選抜を1発で実行する便利関数。"""
    selector = PairwiseSelector(
        panel=panel,
        provenance_family=provenance_family,
    )
    return await selector.select(candidates, axis=axis)


__all__ = [
    "GenerationCandidate",
    "SelectionResult",
    "PairwiseSelector",
    "select_best_of_n",
]
