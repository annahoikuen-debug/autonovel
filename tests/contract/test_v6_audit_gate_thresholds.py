"""tests/contract/test_v6_audit_gate_thresholds.py.

v6 / Step 24: Step 23 で導入した**スコア集約式ゲート**が品質ゲートを
緩めていないことを保証する契約テスト。

保証する4点:

1. 軽微な失敗1件では全文再執筆がしない（「僅1件失敗 = 再執筆」の廃止）
2. 重篤な失敗では再執筆する（ゲートが機能している）
3. 閾値・フラグを変更すると挙動が変わる（ロールバック可能）
4. 集約化しても品質スコアがベースライン（全滅式ゲート）から乖離しない

さらに Step 25（局所パッチ優先）も併せて検証する。
"""

from __future__ import annotations
import asyncio
import os
import statistics
import sys
from pathlib import Path
from typing import Any


import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.audit_agent import (  # noqa: E402
    AUDIT_GATE_PENALTY_SCORE,
    AUDIT_GATE_SEVERITY_WEIGHTS,
    CORE_AUDIT_CRITERIA,
    AuditAgent,
    evaluate_gate,
)
from src.agents.orchestrator import AgentName, AgentContext  # noqa: E402

BLUEPRINT = "第3話 蓝图: ルナは学院で欠けた剣を手放入れる。"


class _FakePromptManager:
    @staticmethod
    def build_fast_plot_screen_prompt(blueprint: str) -> str:
        return f"[fast_plot_screen]\n{blueprint}"

    @staticmethod
    def build_critic_feedback_prompt(
        issue_list: Any = None, draft_content: str = "", blueprint: str = ""
    ) -> str:
        return f"[critic]\n{draft_content}\n{blueprint}"

    @staticmethod
    def build_ability_audit_prompt(
        blueprint: str, settings_json: str, characters_json: str
    ) -> str:
        return f"[ability_audit]\n{blueprint}\n{settings_json}\n{characters_json}"


class _StubLLM:
    """即座に「合格」を返す LLM フェイク。"""

    async def generate_json(self, purpose: str = "", prompt: str = "", **kwargs: Any) -> dict:
        return {"metadata": {"is_valid": True, "is_consistent": True, "feedback": "OK"}}


class _UnifiedOk:
    """定性的判定が「問題なし」を返す UnifiedAuditor 差し替え。"""

    async def audit(self, text: str, character_profiles: str = "", plot_spec: str = ""):
        class _Q:
            critique = ""
            actionable_patch = None

        class _R:
            is_acceptable = True
            final_score = 90.0
            qualitative = _Q()
            conflicts: list[Any] = []

        return _R()


class _NoLearningService:
    async def should_skip_audit_type(self, audit_type: str, field_path: str | None = None):
        return False, 0.0


def _build_agent(verdicts: dict[str, bool] | None = None) -> AuditAgent:
    """指定した audit_id だけを不合格にする AuditAgent を組み立てる。"""
    verdicts = verdicts or {}
    agent = AuditAgent(
        repo=None,
        llm=_StubLLM(),
        prompt_manager=_FakePromptManager(),
        audit_llm=None,
        unified_auditor=_UnifiedOk(),
    )
    agent._learning_service = _NoLearningService()

    async def _screen_plot(blueprint: str) -> tuple[bool, str]:
        return not verdicts.get("fast_screen", False), "screen-fail"

    async def _logical(**kwargs: Any) -> tuple[bool, str, float]:
        return not verdicts.get("logical_consistency", False), "logical-fail", 0.0

    async def _deai(**kwargs: Any) -> tuple[bool, str]:
        return not verdicts.get("deai", False), "deai-fail"

    async def _ability(**kwargs: Any) -> tuple[bool, str, str]:
        return not verdicts.get("ability_consistency", False), "ability-fail", ""

    async def _causal(**kwargs: Any) -> tuple[bool, float, list[str]]:
        if verdicts.get("causal_integrity", False):
            return False, 0.1, ["因果律が崩れている"]
        return True, 1.0, []

    class _StubMonitor:
        async def extract_keywords(self, text: str) -> list[str]:
            return []

        check_integrity = staticmethod(_causal)

    agent._fast_screener.screen_plot = _screen_plot  # type: ignore[method-assign]
    agent._logical_auditor.audit_logical_consistency = _logical  # type: ignore[method-assign]
    agent._deai_auditor.audit = _deai  # type: ignore[method-assign]
    agent._ability_checker.audit_ability_consistency = _ability  # type: ignore[method-assign]
    agent._plot_monitor = _StubMonitor()
    return agent


def _ctx(agent: AuditAgent) -> AgentContext:
    return AgentContext(
        book_id=1,
        branch_id=1,
        ep_num=3,
        artifacts={
            "writing_context": {
                "plot": {"detailed_blueprint": BLUEPRINT},
                "sharp_edges": [],
                "world_settings": "{}",
                "characters_json": "[]",
                "prev_ctx": "",
            },
            "drafted_text": "学院の夜、ルナは欠けた剣を見つめた。",
        },
    )


def _outcomes(agent: AuditAgent, verdicts: dict[str, bool]) -> list[dict[str, Any]]:
    agent = _build_agent(verdicts)
    return asyncio.run(agent.run_audit_phase(_ctx(agent).artifacts["writing_context"], "学院の夜、ルナは欠けた剣を見つめた。", 1, 3))[0]


# ---------------------------------------------------------------------------
# テスト1: 軽微な失敗1件では再執筆しない
# ---------------------------------------------------------------------------


def test_single_minor_failure_does_not_trigger_regeneration() -> None:
    """軽微（medium）な失敗1件では全文再執筆が発生しないこと。"""

    agent = _build_agent({"deai": True})
    result = asyncio.run(agent.execute(_ctx(agent)))

    assert result.should_retry is False, "軽微1件で再執筆している"
    assert result.is_backtrack is False, "軽微1件でバックトラックしている"
    assert result.next_agent == AgentName.ILLUSTRATION, "本文をILLUSTRATIONへ進めていない"
    assert result.artifacts["audit_status"] == "passed_with_warnings"
    assert len(result.artifacts["failed_audits"]) == 1

    # 学習調整（should_downgrade）を受けた1件も同様に続行する
    agent2 = _build_agent({"deai": True})

    async def _downgrade(audit_type: str, field_path: str | None = None):
        return True, 0.5

    agent2._check_learning_adjustment = _downgrade  # type: ignore[method-assign]
    result2 = asyncio.run(agent2.execute(_ctx(agent2)))
    assert result2.should_retry is False, "学習調整済み1件で再執筆している"
    assert result2.artifacts["learning_adjusted_audits"] == ["deai"]


# ---------------------------------------------------------------------------
# テスト2: 重篤な失敗では再執筆する
# ---------------------------------------------------------------------------


def test_critical_failure_triggers_regeneration() -> None:
    """重篤（high複数／監査器例外）な失敗では再執筆が発生すること。"""

    # 1) high 3件（fast_screen / logical / causal）+ medium 1件
    agent = _build_agent(
        {
            "fast_screen": True,
            "logical_consistency": True,
            "causal_integrity": True,
            "deai": True,
        }
    )
    result = asyncio.run(agent.execute(_ctx(agent)))
    gate = result.artifacts.get("gate_evaluation", {})

    assert gate["aggregate_score"] < gate["threshold"], (
        f"重篤4件の集約スコアが閾値を下回っていない: {gate}"
    )
    assert result.should_retry is True, "重篤な失敗で再執筆していない"
    assert result.is_backtrack is True
    assert result.next_agent == AgentName.WRITING
    assert result.artifacts["audit_status"] == "rejected"
    assert result.artifacts["regeneration_directive"], "再生成指示が空"

    # 2) 監査器の例外（critical）
    class _Exploding:
        async def audit(self, **kwargs: Any):
            raise RuntimeError("boom")

    agent2 = _build_agent()
    agent2._deai_auditor = _Exploding()
    result2 = asyncio.run(agent2.execute(_ctx(agent2)))
    assert result2.should_retry is True, "監査器例外で再執筆していない"
    assert result2.artifacts["gate_evaluation"]["critical_failure"] is True


# ---------------------------------------------------------------------------
# テスト3: 閾値とフラグは設定可能（ロールバック可能）
# ---------------------------------------------------------------------------


def test_gate_thresholds_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    """(a) 閾値を上げると再執筆になる (b) フラグを落とすと全滅式に戻る。"""

    def _run() -> Any:
        agent = _build_agent({"deai": True})
        return asyncio.run(agent.execute(_ctx(agent)))

    monkeypatch.delenv("ENABLE_AUDIT_SCORE_GATE", raising=False)
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    strict = _run()
    assert strict.should_retry is True, "閾値 99.0 で再執筆が発生しない"

    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "70.0")
    lenient = _run()
    assert lenient.should_retry is False, "既定閾値 70.0 で再執筆している"

    # ロールバック: 全滅式ゲートへ戻すと軽微1件でも再執筆する
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "false")
    legacy = _run()
    assert legacy.should_retry is True, "全滅式ゲートへロールバックできていない"
    assert legacy.artifacts["gate_evaluation"]["mode"] == "all_or_nothing"

    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "true")
    restored = _run()
    assert restored.artifacts["gate_evaluation"]["mode"] == "score_aggregation"
    assert restored.should_retry is False


# ---------------------------------------------------------------------------
# テスト4: 品質スコアがベースライン（全滅式）から乖離しない
# ---------------------------------------------------------------------------


#: 集計対象の不合格パターン（重篤さの階梯が分かるように並べる）
FAILURE_PATTERNS: list[dict[str, bool]] = [
    {"deai": True},
    {"ability_consistency": True},
    {"fast_screen": True},
    {"logical_consistency": True},
    {"causal_integrity": True},
    {"fast_screen": True, "deai": True},
    {"logical_consistency": True, "deai": True},
    {"causal_integrity": True, "deai": True},
    {"fast_screen": True, "logical_consistency": True, "deai": True},
]


def _measure_regeneration_ratio(gate_enabled: bool) -> float:
    """指定ゲート設定での再執筆率を**実測**して返す（T6 Step 12）。

    ``ENABLE_AUDIT_SCORE_GATE`` は `os.environ` を毎回読むため、
    プロセス全体でこの関数内でだけ切り替える（他テストへの漏れを防ぐ）。
    """
    previous = os.environ.get("ENABLE_AUDIT_SCORE_GATE")
    os.environ["ENABLE_AUDIT_SCORE_GATE"] = "true" if gate_enabled else "false"
    try:
        retries = 0
        for pattern in FAILURE_PATTERNS:
            agent = _build_agent(pattern)
            result = asyncio.run(agent.execute(_ctx(agent)))
            retries += bool(result.should_retry)
        return retries / len(FAILURE_PATTERNS)
    finally:
        if previous is None:
            os.environ.pop("ENABLE_AUDIT_SCORE_GATE", None)
        else:
            os.environ["ENABLE_AUDIT_SCORE_GATE"] = previous


def _score_with_severity(severity: str) -> float:
    """指定 severity の不合格が実際のスコア計算で何点になるかを返す。

    `AuditAgent._build_failed_outcome`（プロダクションの重み付け）を
    直接呼ぶことで、`_build_agent` のモック経路に依存せず
    「severity が計算に効いているか」を観測する。
    """
    from src.agents.audit_agent import AuditCriterion

    agent = _build_agent({"deai": True})
    criterion = AuditCriterion(
        audit_id="deai",
        label="De-AI",
        severity=severity,
        learning_key="deai",
    )
    outcome = agent._build_failed_outcome(
        criterion=criterion,
        feedback="失敗",
        learning_adjusted=False,
        confidence_adjustment=0.0,
        error=None,
    )
    return float(outcome["score"])


def test_quality_score_not_degraded_vs_baseline() -> None:
    """集約化しても品質ゲートが緩まないことを統計的に確認する。

    「緩まない」の定義を4点で検証する:

    1. 不合格があればスコアは 100 を下回り、不合格が増えるほど下がる
    2. 集約ゲートが**通した**話でも、PatchReview とユーザー確認必ず残る
    3. 不合格のある話が「合格（passed）」扱いになることはない
    4. ベースライン（全滅式ゲート）の再執筆率は下がる
    """

    scores: dict[tuple[str, ...], float] = {}
    for pattern in FAILURE_PATTERNS:
        agent = _build_agent(pattern)
        outcomes, _elapsed = asyncio.run(
            agent.run_audit_phase(
                _ctx(agent).artifacts["writing_context"],
                "学院の夜、ルナは欠けた剣を見つめた。",
                1,
                3,
            )
        )
        gate = agent.evaluate_gate(outcomes)
        assert gate["mode"] == "score_aggregation", f"{pattern}: 集約ゲートで判定されていない"
        scores[tuple(sorted(pattern))] = gate["aggregate_score"]

    assert scores, "測定対象の不合格パターンが0件"
    values = list(scores.values())
    assert min(values) >= 0.0 and max(values) <= 100.0, f"スコアが0-100外: {values}"

    # 1) 不合格があれば 100 点にはならない
    assert max(values) < 100.0, "不合格があるのに満点が記録されている"

    # 2) 不合格件数が多いほど平均スコアは下がる（品質低下を反映している）
    singles = [s for k, s in scores.items() if len(k) == 1]
    multiples = [s for k, s in scores.items() if len(k) >= 2]
    assert singles and multiples, "測定用のパターンが不足している"
    assert statistics.mean(multiples) < statistics.mean(singles), (
        f"複数不合格の平均 {statistics.mean(multiples)} が単発 "
        f"{statistics.mean(singles)} を下回っていない"
    )
    assert min(multiples) < min(singles), "最も重い複数不合格が単発不合格を下回っていない"

    # 3) 集約ゲートが通した話でも PatchReview / ユーザー確認は残る
    continued: list[dict[str, Any]] = []
    for pattern in FAILURE_PATTERNS:
        agent = _build_agent(pattern)
        result = asyncio.run(agent.execute(_ctx(agent)))
        if result.should_retry:
            continue
        continued.append(result.artifacts)
        assert result.artifacts["failed_audits"], f"{pattern}: 失敗記録が失われている"
        assert result.artifacts["requires_user_review"] is True, (
            f"{pattern}: ユーザー確認フラグが立たないまま通過している"
        )
        assert "patch_review_id" in result.artifacts, (
            f"{pattern}: PatchReview が作られていない"
        )
        assert result.artifacts["audit_status"] in (
            "passed_with_warnings",
            "patched",
        ), f"{pattern}: 不合格なのに合格扱い: {result.artifacts['audit_status']}"

    # 4) ベースライン（全滅式ゲート）との乖離を**実測**する
    #    T6 Step 12: 以前は `legacy_ratio = 1.0` というハードコードで
    #    「再執筆率が 1.0 より小さい」ことしかアサートしておらず、
    #    ゲート集約の効果を検証していなかった。
    #    ここでは実際に `ENABLE_AUDIT_SCORE_GATE=0`（旧 all-or-nothing）と
    #    `=1`（新スコア集約）の両方で走らせて比率を比較する。
    legacy_ratio = _measure_regeneration_ratio(gate_enabled=False)
    score_ratio = _measure_regeneration_ratio(gate_enabled=True)
    print(
        f"[実測] 再執筆比率: all-or-nothing {legacy_ratio:.0%} "
        f"→ score-aggregation {score_ratio:.0%}"
    )
    assert legacy_ratio > score_ratio, (
        f"スコア集約が再執筆率を下げていない: "
        f"legacy {legacy_ratio:.0%} <= score {score_ratio:.0%}"
    )
    # 旧ゲートが「1件でも落ちたら全滅」であったことの確認（実測ベースライン）
    assert legacy_ratio == 1.0, (
        f"旧ゲートの実測ベースラインが 100% ではない: {legacy_ratio:.0%}。"
        "FAILURE_PATTERNS やゲートの挙動が変わった可能性がある"
    )


# ---------------------------------------------------------------------------
# 追加: severity 重み付けの性質
# ---------------------------------------------------------------------------


def test_severity_weighting_actually_affects_score() -> None:
    """severity 重みが**実際のゲート計算**に効くことを観測で証明する。

    T6 Step 12: 以前は `AUDIT_GATE_SEVERITY_WEIGHTS` の定数値だけを
    アサートしており、プロダクション経路を一切通していなかった
    （定数が書き換わってもテストは緑のままだった）。
    ここでは実キーで `low`（軽微）と `critical`（重篤）の実スコア差を観測する。

    注意: `AUDIT_GATE_PENALTY_SCORE` は「減点」ではなく**加点残**である。
    `critical=0.0` は「100点から満額減点された」= 最も重い、という意味。
    """
    mild = _score_with_severity("low")
    critical = _score_with_severity("critical")
    print(
        f"[実測] severity 別 score（加点残）: low={mild:.1f} "
        f"critical={critical:.1f}"
    )
    assert critical < mild, (
        "severity がスコア計算に反映されていない"
        f"（low={mild:.1f}, critical={critical:.1f}）。"
        "WEIGHT 定数の定義だけが変わっている疑いがある"
    )
    # 尚、定数の並び順そのものも併せて固定する（意味の入れ替え防止）
    assert (
        AUDIT_GATE_SEVERITY_WEIGHTS["low"]
        < AUDIT_GATE_SEVERITY_WEIGHTS["medium"]
        < AUDIT_GATE_SEVERITY_WEIGHTS["high"]
        < AUDIT_GATE_SEVERITY_WEIGHTS["critical"]
    )
    assert (
        AUDIT_GATE_PENALTY_SCORE["critical"]
        < AUDIT_GATE_PENALTY_SCORE["high"]
        < AUDIT_GATE_PENALTY_SCORE["medium"]
        < AUDIT_GATE_PENALTY_SCORE["low"]
    )


# ---------------------------------------------------------------------------
# 追加: Step 25（局所パッチ優先）
# ---------------------------------------------------------------------------


def test_local_patch_is_preferred_over_full_rewrite() -> None:
    """重篤失敗でも、局所パッチが適用できる場合は全文再執筆しないこと。"""

    class _PatchableReport:
        is_acceptable = False
        final_score = 55.0
        conflicts: list[Any] = []
        qualitative = None

    class _UnifiedWithPatch:
        def __init__(self) -> None:
            self.report = _PatchableReport()

        async def audit(self, text: str, character_profiles: str = "", plot_spec: str = ""):
            class _Q:
                critique = "AI感がある"
                actionable_patch = "雨の音だけが響いていた。"

            self.report.qualitative = _Q()
            return self.report

    agent = _build_agent(
        {
            "fast_screen": True,
            "logical_consistency": True,
            "causal_integrity": True,
            "deai": True,
        }
    )

    class _AlwaysFailCausal:
        def extract_keywords(self, text: str) -> list[str]:
            return []

        async def check_integrity(self, **kwargs: Any):
            return False, 0.1, ["因果律が崩れている"]

    agent._plot_monitor = _AlwaysFailCausal()
    agent._unified_auditor = _UnifiedWithPatch()
    agent._unified_auditor_resolved = True

    result = asyncio.run(agent.execute(_ctx(agent)))

    assert result.artifacts["gate_evaluation"]["requires_regeneration"] is True, (
        "ゲートが再執筆と判定していない（前提が崩れている）"
    )
    assert result.should_retry is False, "局所パッチで済んだのに再執筆している"
    assert result.artifacts["patch_strategy"] == "actionable_patch"
    assert result.artifacts["patched_text"].endswith("雨の音だけが響いていた。")


def test_safe_replace_patch_is_preferred() -> None:
    """SafeReplacer で置換できる場合は strategy=safe_replace になること。"""

    class _Conflict:
        current_value = "Certainly, the rain fell."
        suggested_value = "雨が静かに降っていた。"

    class _Q:
        critique = "定型表現"
        actionable_patch = None

    class _Report:
        is_acceptable = False
        final_score = 40.0
        conflicts = [_Conflict()]
        qualitative = _Q()

    class _UnifiedWithConflict:
        async def audit(self, text: str, character_profiles: str = "", plot_spec: str = ""):
            return _Report()

    agent = _build_agent(
        {
            "fast_screen": True,
            "logical_consistency": True,
            "causal_integrity": True,
            "deai": True,
        }
    )

    class _AlwaysFailCausal:
        def extract_keywords(self, text: str) -> list[str]:
            return []

        async def check_integrity(self, **kwargs: Any):
            return False, 0.1, ["因果律が崩れている"]

    agent._plot_monitor = _AlwaysFailCausal()
    agent._unified_auditor = _UnifiedWithConflict()
    agent._unified_auditor_resolved = True

    ctx = _ctx(agent)
    ctx.artifacts["drafted_text"] = "Certainly, the rain fell. 長い夜だった。"
    result = asyncio.run(agent.execute(ctx))

    assert result.artifacts["patch_strategy"] == "safe_replace"
    assert "Certainly, the rain fell." not in result.artifacts["patched_text"]
    assert "雨が静かに降っていた。" in result.artifacts["patched_text"]


def test_full_rewrite_fallback_when_patch_impossible() -> None:
    """局所パッチが適用できない場合は全文再執筆へフォールバックすること。"""

    class _NoPatch:
        async def audit(self, text: str, character_profiles: str = "", plot_spec: str = ""):
            class _Q:
                critique = "重大"
                actionable_patch = None

            class _R:
                is_acceptable = False
                final_score = 20.0
                conflicts = []
                qualitative = _Q()

            return _R()

    agent = _build_agent(
        {
            "fast_screen": True,
            "logical_consistency": True,
            "causal_integrity": True,
            "deai": True,
        }
    )

    class _AlwaysFailCausal:
        def extract_keywords(self, text: str) -> list[str]:
            return []

        async def check_integrity(self, **kwargs: Any):
            return False, 0.1, ["因果律が崩れている"]

    agent._plot_monitor = _AlwaysFailCausal()
    agent._unified_auditor = _NoPatch()
    agent._unified_auditor_resolved = True

    result = asyncio.run(agent.execute(_ctx(agent)))
    assert "patched_text" not in result.artifacts, "パッチ不可能なのに patched_text がある"
    assert result.should_retry is True
    assert result.next_agent == AgentName.WRITING


# ---------------------------------------------------------------------------
# 追加: 定性的判断（UnifiedAuditor）統合の 1対1 対応
# ---------------------------------------------------------------------------


def test_all_five_audit_items_are_preserved() -> None:
    """UnifiedAuditor 統合後も既存5監査の判定項目が1対1で残っていること。"""

    assert [c.audit_id for c in CORE_AUDIT_CRITERIA] == [
        "fast_screen",
        "logical_consistency",
        "deai",
        "ability_consistency",
        "causal_integrity",
    ]
    assert all(c.blocking for c in CORE_AUDIT_CRITERIA), "既存5監査のいずれかが非ブロック化されている"
    assert all(c.learning_key == c.audit_id for c in CORE_AUDIT_CRITERIA), (
        "学習データキーが1対1で対応していない"
    )


def test_unified_auditor_failure_is_non_blocking_by_default() -> None:
    """UnifiedAuditor が評価不成立でもゲートを落とさない（fail-open、v6-A2 の既定）。"""

    class _Degraded:
        async def audit(self, text: str, character_profiles: str = "", plot_spec: str = ""):
            raise RuntimeError("LLM未設定")

    agent = _build_agent()
    agent._unified_auditor = _Degraded()
    agent._unified_auditor_resolved = True

    result = asyncio.run(agent.execute(_ctx(agent)))
    assert result.artifacts["audit_status"] == "passed"
    unified_outcome = [
        o for o in agent.last_gate_evaluation["scored_audit_ids"]
    ]
    assert "unified_qualitative" not in unified_outcome, (
        "既定で UnifiedAuditor がゲート集計に混入している"
    )


def test_evaluate_gate_module_helper_is_callable() -> None:
    """ゲート集約が副作用なく再利用可能なモジュールヘルパであること。"""

    outcomes = [
        {
            "audit_id": c.audit_id,
            "passed": True,
            "score": 100.0,
            "weight": 1.0,
            "blocking": True,
            "effective_severity": None,
        }
        for c in CORE_AUDIT_CRITERIA
    ]
    evaluation = evaluate_gate(outcomes)
    assert evaluation["aggregate_score"] == 100.0
    assert evaluation["requires_regeneration"] is False
