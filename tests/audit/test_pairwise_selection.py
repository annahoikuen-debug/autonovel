"""M5-A: PairwiseSelector テスト。

Best-of-N ペアワイズ選抜のロジックを検証する。
JudgePanel はモックで代用し、ペアワイズ結果を制御する。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.audit.judge_panel import PairwiseVerdict
from src.audit.pairwise_selection import (
    GenerationCandidate,
    PairwiseSelector,
    SelectionResult,
    select_best_of_n,
)


class _FakePanel:
    """JudgePanel をモック。pairwise の結果を制御する。"""

    def __init__(self, verdict_map: dict[tuple[str, str], str] | None = None, fail: bool = False):
        self._verdict_map = verdict_map or {}
        self.fail = fail
        self.call_count = 0

    async def pairwise(
        self,
        a: str,
        b: str,
        axis: str = "overall",
        *,
        provenance_family: str | None = None,
    ) -> PairwiseVerdict:
        self.call_count += 1
        if self.fail:
            raise RuntimeError("pairwise failure")
        key = (a, b)
        if key in self._verdict_map:
            winner = self._verdict_map[key]
        else:
            # デフォルト: テキスト長が長い方を勝ちとする
            winner = "A" if len(a) >= len(b) else "B"
        return PairwiseVerdict(
            winner=winner,  # type: ignore[arg-type]
            axis=axis,
            judge_verdicts=[],
            agreement_rate=1.0,
        )


def _make_candidates(texts: list[str], static_scores: list[float] | None = None) -> list[GenerationCandidate]:
    if static_scores is None:
        static_scores = [50.0 + i * 10.0 for i in range(len(texts))]
    return [
        GenerationCandidate(text=t, static_score=s, generation_index=i)
        for i, (t, s) in enumerate(zip(texts, static_scores))
    ]


# ---- インスタンス作成 ----


def test_selector_creation():
    """PairwiseSelector が作成できる。"""
    panel = _FakePanel()
    selector = PairwiseSelector(panel=panel)
    assert selector.top_n_from_static == 2
    assert selector.provenance_family is None


def test_selector_top_n_custom():
    """top_n_from_static をカスタムできる。"""
    panel = _FakePanel()
    selector = PairwiseSelector(panel=panel, top_n_from_static=3)
    assert selector.top_n_from_static == 3


# ---- 候補1件 ----


@pytest.mark.asyncio
async def test_select_single_candidate_static_only():
    """候補1件なら static_only で返される。"""
    panel = _FakePanel()
    selector = PairwiseSelector(panel=panel)
    candidates = _make_candidates(["本文Aです。"], [80.0])

    result = await selector.select(candidates)

    assert isinstance(result, SelectionResult)
    assert result.method == "static_only"
    assert result.selected_index == 0
    assert result.selected_text == "本文Aです。"
    assert result.selected_static_score == 80.0
    assert result.pairwise_verdicts == []
    assert result.n_candidates == 1
    assert panel.call_count == 0  # ペアワイズは呼ばれない


# ---- 複数候補: 静的上位1位がそのまま勝つ ----


@pytest.mark.asyncio
async def test_select_static_top_wins_without_pairwise():
    """静的上位1件のみならペアワイズ不要。"""
    panel = _FakePanel()
    selector = PairwiseSelector(panel=panel, top_n_from_static=1)
    candidates = _make_candidates(["短い。", "長い本文です。もっと長いです。"], [90.0, 50.0])

    result = await selector.select(candidates)

    assert result.method == "static_only"
    assert result.selected_index == 0  # 静的スコア90の方
    assert panel.call_count == 0


# ---- 複数候補: ペアワイズ決勝 ----


@pytest.mark.asyncio
async def test_select_pairwise_champion_changes():
    """ペアワイズで挑戦者が勝つとチャンピオンが交代する。"""
    panel = _FakePanel(
        verdict_map={
            ("本文Aです。", "本文Bです。"): "B",  # 第2引数(B=挑戦者)が勝ち
            ("本文Bです。", "本文Cです。"): "B",  # 第2引数(C=挑戦者)が勝ち
        }
    )
    selector = PairwiseSelector(panel=panel, top_n_from_static=3)
    candidates = _make_candidates(
        ["本文Aです。", "本文Bです。", "本文Cです。"], [80.0, 70.0, 60.0]
    )

    result = await selector.select(candidates)

    assert result.method == "pairwise"
    assert result.selected_index == 2  # C が最終チャンピオン
    assert result.selected_text == "本文Cです。"
    assert len(result.pairwise_verdicts) == 2  # A vs B、勝者 vs C


@pytest.mark.asyncio
async def test_select_pairwise_tie_breaks_by_static():
    """ペアワイズ引き分けは静的スコアで決着。"""
    panel = _FakePanel(verdict_map={("A", "B"): "tie"})
    selector = PairwiseSelector(panel=panel)
    candidates = _make_candidates(["A", "B"], [50.0, 90.0])

    result = await selector.select(candidates)

    assert result.selected_index == 1  # 静的スコア90の B が勝つ


# ---- ペアワイズ失敗時のフォールバック ----


@pytest.mark.asyncio
async def test_select_pairwise_failure_falls_back_to_static():
    """ペアワイズ失敗時は静的スコアでフォールバック。"""
    panel = _FakePanel(fail=True)
    selector = PairwiseSelector(panel=panel)
    candidates = _make_candidates(["低スコア", "高スコアです。"], [30.0, 90.0])

    result = await selector.select(candidates)

    assert result.method == "fallback_first"
    assert result.selected_index == 1  # 静的スコア高い方


# ---- 便利関数 select_best_of_n ----


@pytest.mark.asyncio
async def test_select_best_of_n_convenience():
    """select_best_of_n 便利関数が動作する。"""
    panel = _FakePanel()
    candidates = _make_candidates(["Xです。", "Yです。より長いテキストです。"], [40.0, 60.0])

    result = await select_best_of_n(candidates, panel, axis="overall")

    assert isinstance(result, SelectionResult)
    assert result.n_candidates == 2


# ---- 空リストエラー ----


@pytest.mark.asyncio
async def test_select_empty_raises():
    """空リストは ValueError。"""
    panel = _FakePanel()
    selector = PairwiseSelector(panel=panel)
    with pytest.raises(ValueError):
        await selector.select([])
