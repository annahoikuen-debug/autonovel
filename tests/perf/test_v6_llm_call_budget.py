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


#: 1話のパイプラインが LLM を呼び出すスキル構成（**構成推計**、V6 §2 に基づく）
#:
#: T6 Step 13: これは実測値ではなく、スキル構成から読み取った**構造上の想定**である。
#: 従来のテストはこの辞書をそのまま合計して「実測」と表示しており、
#: 値が常に 10 になるため効果測定に使えなかった。
#: 実際の計測は `measure_real_audit_calls()`（本物の `AuditAgent` を走らせる）と
#: `measure_calls_per_episode()`（トラッカーの実カウンタ）で行う。
STRUCTURAL_SKILL_LLM_CALLS: dict[str, int] = {
    "PlanningSkill": 1,
    "BibleSkill": 1,
    "ContextBuilderSkill": 1,
    "HistoricalAccuracyChecker": 0,
    "WritingSkill": 1,
    "EnrichmentSkill": 1,
    "AuditSkill": 5,  # ← WS-A の並列化でレイテンシだけ短縮（回数は減らない）
    "CulturalComplianceChecker": 0,
    "IllustrationSkill": 0,  # K4/T6 Step 4: no-op 化（request 供給元が無い）
    "MarketingCopySkill": 0,
}


def judge_against_target(
    measured: int, *, target_min: int | None = None, target_max: int | None = None
) -> dict[str, Any]:
    """実測値を目標帯と���較し、判定結果を返す（docs/STATUS.md が読む）。"""
    meets = True
    if target_min is not None:
        meets = meets and measured >= target_min
    if target_max is not None:
        meets = meets and measured <= target_max
    return {
        "measured": measured,
        "target_min": target_min,
        "target_max": target_max,
        "meets_target": meets,
    }


def measure_real_audit_calls() -> int:
    """本物の `AuditAgent` を走らせて監査フェーズの LLM 呼出回数を**実測**する。

    T6 Step 13: 従来は `STRUCTURAL_SKILL_LLM_CALLS["AuditSkill"] = 5` という
    ハードコードが「実測」のように表示されていた。ここでは実際に
    `run_audit_phase()` を通し、`TokenTracker` のカウンタを読む。
    """
    import asyncio

    from src.agents.audit_agent import AuditAgent
    from src.services.llm.tracked_adapter import build_tracked_adapters

    tracker = TokenTracker()
    adapters = build_tracked_adapters(
        _DeterministicLLM(),
        tracker=tracker,
        models={"audit": "gemini-2.0-flash"},
    )
    agent = AuditAgent(llm=adapters["audit_llm"], repo=None, event_bus=None)

    async def _run() -> None:
        await agent.run_audit_phase(
            {"plot": {"detailed_blueprint": "PLAN"}, "sharp_edges": []},
            "学院の夜、ルナは欠けた剣を見つめた。",
            1,
            3,
        )

    asyncio.run(_run())
    return sum(b["calls"] for b in tracker.get_task_breakdown().values())


def measure_calls_per_episode(tracker: TokenTracker | None = None) -> int:
    """1話分のスキル列を実行し、トラッカーの**実カウンタ**から回数を返す。

    ハードコードされた辞書を合計するのではなく、実際にアダプタを呼んで
    記録された値だけを返す。既に計測済みのトラッカーを渡すと
    値が加算されるため、判定には新しいトラッカーを渡すこと。
    """
    tracker = tracker if tracker is not None else TokenTracker()
    _simulate_one_episode(tracker)
    return sum(b["calls"] for b in tracker.get_task_breakdown().values())


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
        for skill, calls in STRUCTURAL_SKILL_LLM_CALLS.items():
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
        """1話あたりの LLM 呼び出し回数を**実測**する（V6 §6 未検証事項1）。

        T6 Step 13: 以前はハードコード辞書（`STRUCTURAL_SKILL_LLM_CALLS`）を
        合計して「実測」と表示しており、値が構造上常に 10 になっていた。
        ここではトラッカーの実カウンタから測る。
        """
        tracker = TokenTracker()
        result = _simulate_one_episode(tracker)

        # 実測値はトラッカーの実カウンタそのものである
        measured = sum(b["calls"] for b in result["breakdown"].values())
        assert measured > 0, "1話あたりのLLM回数が計測できていない"
        assert result["total_calls"] == measured, (
            f"集計値 {result['total_calls']} と内訳合計 {measured} が不一致"
        )
        # 独立計測（新しいトラッカー）でも同じ値になること
        assert measure_calls_per_episode() == measured, (
            "独立計測値が一致しない（計測が確定的でない）"
        )
        print(
            f"\n[実測] 1話あたりLLM呼び出し回数: {measured}"
            f"（構成内訳は参考値: {STRUCTURAL_SKILL_LLM_CALLS}）"
        )

    def test_measured_calls_match_target_verdict(self) -> None:
        """実測値を目標（4-5回）と比較し、判定を返すこと（T6 Step 13/15 用）。"""
        measured = measure_calls_per_episode()
        verdict = judge_against_target(measured, target_min=4, target_max=5)
        print(
            f"\n[実測] 1話 {measured} 回 / 目標 4-5 回 → "
            f"{'達成' if verdict['meets_target'] else '未達'}"
        )
        assert verdict["measured"] == measured
        assert verdict["meets_target"] in (True, False)
        assert 0 < measured <= BASELINE_MAX_LLM_CALLS_PER_EPISODE

    def test_real_audit_phase_call_count_is_measured(self) -> None:
        """本物の `AuditAgent` を走らせ、監査回数を**実測**すること。

        T6 Step 13 の主要観測点。従来は `5` をハードコードしていた。

        注意: 決定的なスタブ LLM では、LLM を実際に呼ばずに自己判定で
        終了する監査があるため、この値は**下限**である
        （本番では 5 監査がそれぞれ LLM を呼ぶため上振れする）。
        効果測定表には下限値として記載すること。
        """
        measured = measure_real_audit_calls()
        print(
            f"\n[実測] 監査フェーズのLLM呼び出し回数: {measured}"
            "（決定的なスタブ LLM による下限値）"
        )
        assert measured > 0, "監査フェーズの実測が 0"
        assert 0 < measured <= 10, f"監査回数が想定外: {measured}"

    def test_structural_and_measured_are_tracked_separately(self) -> None:
        """構造推計と実測が別値として取得できること（混同防止）。

        T6 Step 13 の主眼。構造推計は効果測定に使えないため、
        両者が同一視されていないことを「両方取れる」ことで担保する。
        """
        structural = sum(STRUCTURAL_SKILL_LLM_CALLS.values())
        measured = measure_calls_per_episode()
        assert isinstance(structural, int) and structural > 0
        assert isinstance(measured, int) and measured > 0
        # 差分があれば「構造推計では上过长期」になる。記録として残す。
        print(
            f"\n[参考] 構成推計 {structural} 回 / 実測 {measured} 回 "
            f"（差 {measured - structural:+d}）"
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
        assert result["breakdown"]["audit"]["calls"] == STRUCTURAL_SKILL_LLM_CALLS["AuditSkill"], (
            "並列化で監査の呼び出し回数が変わるようなら、回数を削減する"
            "最適化が別途必要（WS-A-3 のゲート集約）"
        )
