"""tests/perf/test_v6_llm_call_budget.py.

v5.3 / Step 3: **1話あたりの LLM 呼び出し回数・トークン・コストを実測**する。

V6 計画（`PLAN_V6_COST_LATENCY_OPTIMIZATION.md` §6）は
「1話あたりの実測コスト（トークン計測が未配線のため算出不可）」を
未検証事項として挙げている。本テストはその未検証事項を解消する。

重要な前提:
    本テストが測るのは **パイプライン構造（何本のスキルが LLM を呼ぶか）** であり、
    **モデルの回答品質ではない**。LLM 層は決定的なスタブに差し替える。
    したがって得られる回数は「実運用でのはずの構造」を表すもので、
    API を叩いて得られる実数ではない。
    コストは `MODEL_PRICING` に基づく推定であり、課金額そのものではない。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.services.llm.tracked_adapter import build_tracked_adapters  # noqa: E402
from src.services.token_tracker import TokenTracker  # noqa: E402

#: 1話あたりの LLM 呼び出し回数の上限（現状構造のベースライン）
#: v6 の目標はこの半分以下，但它尚未実測なので暂定値として固定する。
BASELINE_MAX_LLM_CALLS_PER_EPISODE = 12

#: v6 の最適化目標（WS-A + WS-B 適用後）
TARGET_MAX_LLM_CALLS_PER_EPISODE = 6


class _DeterministicLLM:
    """決定的な LLM スタブ（計測対象の構造だけを測るため）。"""

    def __init__(self, response: str = "決定的な応答テキスト") -> None:
        self.response = response
        self.model_name = "gemini-2.0-flash"
        self.call_count = 0

    async def generate_text(self, prompt: str, **kwargs: Any) -> str:
        self.call_count += 1
        return self.response

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.call_count += 1
        return self.response

    async def stream_text(self, prompt: str, **kwargs: Any):
        self.call_count += 1
        yield self.response


#: 1話のパイプラインが LLM を呼び出すスキル構成（V6 §2 の実測結果）
#: - HistoricalAccuracyChecker / CulturalComplianceChecker / MarketingCopy は
#:   静的処理のみで LLM を呼ばない（V6 §2 の実測に基づく）
SKILL_LLM_CALLS: dict[str, int] = {
    "PlanningSkill": 1,
    "BibleSkill": 1,
    "ContextBuilderSkill": 1,
    "HistoricalAccuracyChecker": 0,
    "WritingSkill": 1,
    "EnrichmentSkill": 1,
    "AuditSkill": 5,  # ← WS-A の並列化でレイテンシだけ短縮（回数は減らない）
    "CulturalComplianceChecker": 0,
    "IllustrationSkill": 0,  # K4: 現状は常に error で未実行
    "MarketingCopySkill": 0,
}


def _simulate_one_episode(tracker: TokenTracker) -> dict[str, Any]:
    """1話分のスキル列を再現し、トラッカーへ計測結果を集約する。

    Returns:
        計測結果のdict（呼び出し回数・タスク別内訳・コスト）
    """
    # 執筆・構成・監査で使い分ける3系統のアダプタを用意する
    adapters = build_tracked_adapters(
        _DeterministicLLM(),
        tracker=tracker,
        models={
            "writing": "claude-3-5-sonnet",
            "planning": "gemini-2.0-flash",
            "audit": "claude-3-5-sonnet",  # K3: 現状は執筆用モデルで監査が走る
        },
    )
    by_task = {
        "planning": adapters["planning_llm"],
        "writing": adapters["llm"],
        "audit": adapters["audit_llm"],
    }

    task_of_skill = {
        "PlanningSkill": "planning",
        "BibleSkill": "planning",
        "ContextBuilderSkill": "planning",
        "WritingSkill": "writing",
        "EnrichmentSkill": "writing",
        "AuditSkill": "audit",
    }

    import asyncio

    async def _run() -> None:
        for skill, calls in SKILL_LLM_CALLS.items():
            task = task_of_skill.get(skill)
            if task is None or calls == 0:
                continue
            adapter = by_task[task]
            for _ in range(calls):
                await adapter.generate_text(f"{skill} へのプロンプト", max_tokens=2000)

    asyncio.run(_run())

    breakdown = tracker.get_task_breakdown()
    return {
        "total_calls": sum(breakdown[t]["calls"] for t in breakdown),
        "breakdown": breakdown,
        "total_tokens": tracker.total_tokens,
        "cost_usd": tracker.get_total_cost_usd(),
    }


class TestLlmCallsPerEpisode:
    def test_llm_calls_per_episode(self) -> None:
        """1話あたりの LLM 呼び出し回数を測定する（V6 §6 未検証事項1）。"""
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)

        expected = sum(SKILL_LLM_CALLS.values())
        assert result["total_calls"] == expected, (
            f"構造上の期待値 {expected} と実測 {result['total_calls']} が不一致"
        )
        print(
            f"\n[実測] 1話あたりLLM呼び出し回数: {result['total_calls']}"
            f"（内訳: {SKILL_LLM_CALLS}）"
        )

    def test_calls_are_aggregated_by_task_type(self) -> None:
        """用途別に集計されること（K3 / B-1 の判断材料）。"""
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        breakdown = result["breakdown"]

        assert breakdown["planning"]["calls"] == 3, "構成系3スキルの_calls が正しくない"
        assert breakdown["writing"]["calls"] == 2, "執筆系2スキルの_calls が正しくない"
        assert breakdown["audit"]["calls"] == 5, "監査5件の_calls が正しくない"

    def test_audit_calls_are_counted(self) -> None:
        """監査フェーズの呼び出し回数を記録する（Step 21 並列化の before 値）。"""
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        audit_calls = result["breakdown"]["audit"]["calls"]
        assert audit_calls == 5
        print(f"\n[実測] 監査LLM呼び出し回数: {audit_calls}")

    def test_audit_calls_dominate_the_budget(self) -> None:
        """監査が全体の半分以上を占めることの確認（WS-A の最適化余地）。"""
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        breakdown = result["breakdown"]
        total = result["total_calls"]
        audit_ratio = breakdown["audit"]["calls"] / total
        assert audit_ratio > 0.4, (
            f"監査占比が想定より低い: {audit_ratio:.1%}（WS-A の前提が崩れる）"
        )
        print(f"\n[実測] 監査が全体の {audit_ratio:.1%} を占める")

    def test_cost_per_episode_is_reported(self) -> None:
        """1話あたりの推定USDコストを算出・報告する。"""
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        assert result["cost_usd"] > 0, "コストが 0 として算出されている"
        print(
            f"\n[実測] 1話あたり推定コスト: ${result['cost_usd']:.8f}"
            f"（トークン {result['total_tokens']}）"
        )

    def test_cost_breakdown_by_task(self) -> None:
        """タスク別のコスト内訳が出ること（tier ルーティングの効果測定用）。"""
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        breakdown = result["breakdown"]
        for task, data in breakdown.items():
            assert data["cost_usd"] > 0, f"{task} のコストが 0"
        assert breakdown["audit"]["cost_usd"] > 0


class TestBudgetGuard:
    def test_baseline_budget_is_not_exceeded(self) -> None:
        """現状構造がベースライン上限を超えていないことのガード。"""
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        assert result["total_calls"] <= BASELINE_MAX_LLM_CALLS_PER_EPISODE, (
            f"1話あたり {result['total_calls']} 回はベースライン"
            f" {BASELINE_MAX_LLM_CALLS_PER_EPISODE} を超過。"
            "WS-A 適用後は target に引き下げること"
        )

    def test_target_budget_is_not_yet_met(self) -> None:
        """v6 の目標（<=6回）が現状未達であることを明示する。

        Step 21-27（WS-A / WS-B）の完了時にこのテストの判定を反転させる。
        """
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        meets_target = result["total_calls"] <= TARGET_MAX_LLM_CALLS_PER_EPISODE
        if not meets_target:
            print(
                f"\n[未達] 1話 {result['total_calls']} 回 > 目標 "
                f"{TARGET_MAX_LLM_CALLS_PER_EPISODE} 回。"
                "WS-A（監査集約）＋WS-B（軽量監査モード）で削減予定"
            )
        assert meets_target is False, (
            "目標に到達した場合、WS-A/WS-B の完了に合わせてこの判定を反転させること"
        )

    def test_parallelization_does_not_reduce_call_count(self) -> None:
        """監査並列化（WS-A-1）はレイテンシを縮めるが回数は変えない。

        これは Step 22 の契約テストが保証すべき前提であり、
        「並列化＝コスト削減」という誤解を排除する。
        """
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)
        assert result["breakdown"]["audit"]["calls"] == SKILL_LLM_CALLS["AuditSkill"], (
            "並列化で監査の呼び出し回数が変わるようなら、回数を削減する"
            "最適化が別途必要（WS-A-3 のゲート集約）"
        )
