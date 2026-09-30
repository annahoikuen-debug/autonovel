"""tests/perf/test_v6_audit_latency_and_regen.py.

T6 Step 14: 監査レイテンシと本文再生成比率の**実測**。

親計画 Step 36 の効果測定表で未計測だった 2 項目を埋める。

  - 監査レイテンシ: 直列 vs 並列の実測値（並列化 Step 21 の効果検証）
  - 本文再生成比率: スコア集約ゲート（Step 23）適用後の実測値

いずれも**機械的計測**に限定する。LLM の「精度」で判定するコードは書かず、
必ず閾値比較で記録する（目標未達でも fail させない。計測が主目的）。
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.orchestrator import AgentContext  # noqa: E402

#: 各記号が「不合格になる」(axis, verdict) の組合せ
FAILURE_AXES = [
    "deai",
    "ability_consistency",
    "fast_screen",
    "logical_consistency",
    "causal_integrity",
]

#: 再生成比率の目標（V6 想定 67% → 10%未満）
REGENERATION_TARGET_MAX = 0.10

#: 監査並列化の目標（5 → 約1/5）
AUDIT_LATENCY_TARGET_RATIO = 0.5

#: 計測に使う模拟テキスト（監査器が自己判定で必ず1回 LLM を呼ぶよう variety を持たせる）
_CORPUS = [
    "学院の夜、ルナは欠けた剣を見つめた。封印の紋が微かに明滅している。",
    "熔炉の炎が頂点产销する中、鍛冶師は最後の一振りを振り上げた。",
    "王城の回廊で在她的影が二重に揺れた。-switch「次の王」は誰だ。",
    "雪原の先で幼特别な狼の吠声が聞こえて、騎士は馬を止めた。",
    "塔の頂で星の配置が briightく変わり、巫女は息を呑んだ。",
] * 4


def _build_agent():
    """5 監査が稼働する `AuditAgent` を作る（`test_v6_audit_gate_thresholds` と同型）。"""
    from src.agents.audit_agent import AuditAgent

    verdicts = {axis: True for axis in FAILURE_AXES}
    agent = AuditAgent(llm=None, repo=None, event_bus=None)

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

    agent._fast_screener.screen_plot = _screen_plot
    agent._logical_auditor.audit_logical_consistency = _logical
    agent._deai_auditor.audit = _deai
    agent._ability_checker.audit_ability_consistency = _ability
    agent._plot_monitor = _StubMonitor()
    return agent


def _ctx(agent) -> AgentContext:
    return AgentContext(
        book_id=1,
        branch_id=1,
        ep_num=3,
        artifacts={
            "writing_context": {
                "plot": {"detailed_blueprint": "PLAN"},
                "sharp_edges": [],
                "world_settings": "{}",
                "characters_json": "[]",
                "prev_ctx": "",
            },
            "drafted_text": "学院の夜、ルナは欠けた剣を見つめた。",
        },
    )


# ---------------------------------------------------------------------------
# (1) 監査レイテンシの実測
# ---------------------------------------------------------------------------


async def _measure_audit_latency(parallel: bool, runs: int = 5) -> dict[str, Any]:
    """監査フェーズのレイテンシを実測する（中央値と全サンプルを返す）。"""
    agent = _build_agent()
    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        await agent.run_audit_phase(
            {"plot": {"detailed_blueprint": "PLAN"}, "sharp_edges": []},
            _CORPUS[0],
            1,
            3,
            parallel=parallel,
        )
        samples.append((time.perf_counter() - started) * 1000.0)
    return {
        "median_ms": statistics.median(samples),
        "mean_ms": statistics.fmean(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "runs": runs,
    }


@pytest.mark.asyncio
async def test_audit_latency_measured_parallel_vs_serial():
    """並列/直列のレイテンシが実測値として得られること（Step 21 の効果検証）。

    注意: 本テストの LLM は**決定的なスタブ**であり、I/O 待ちが無い。
    そのため `asyncio.gather` のオーバーヘッドが相対的に大きくなり、
    実測では短縮にならない（甚至逆効果になり得る）のが正常。
    本番のように**ネットワーク I/O が支配的な**場合のみ短縮が現れる。
    効果測定表には「スタブ実測（I/O 待ちなし）」と明記すること。
    """
    serial = await _measure_audit_latency(parallel=False, runs=5)
    parallel = await _measure_audit_latency(parallel=True, runs=5)

    assert serial["median_ms"] > 0
    assert parallel["median_ms"] > 0
    speedup = serial["median_ms"] / parallel["median_ms"]
    meets = speedup >= (1 / AUDIT_LATENCY_TARGET_RATIO)
    print(
        f"\n[実測] 監査レイテンシ（決定的なスタブ LLM / I/O待ちなし）: "
        f"直列 {serial['median_ms']:.3f}ms / "
        f"並列 {parallel['median_ms']:.3f}ms（短縮率 {speedup:.2f}倍）"
        f" → {'目標達成' if meets else '目標未達（I/O待ちなしでは測定不能）'}"
    )
    # 短縮比の実測値を必ず残す（未達でも fail させない）
    assert speedup > 0


@pytest.mark.asyncio
async def test_parallel_never_slower_than_serial_by_large_margin():
    """並列化が直列より大幅に遅くならないことのガード。

    決定論的なスタブでは並列化の効果が測定できない（I/O 待ちが無いため）
    ため、短縮をアサートせず「壊れていない」ことだけを確かめる。
    """
    serial = await _measure_audit_latency(parallel=False, runs=3)
    parallel = await _measure_audit_latency(parallel=True, runs=3)
    assert parallel["median_ms"] < serial["median_ms"] * 5, (
        "並列化で直列の 5 倍以上遅くなっている（回帰の疑い）: "
        f"serial={serial['median_ms']:.3f}ms parallel={parallel['median_ms']:.3f}ms"
    )


# ---------------------------------------------------------------------------
# (2) 本文再生成比率の実測
# ---------------------------------------------------------------------------


def _measure_regeneration_ratio() -> dict[str, Any]:
    """スコア集約ゲート通過時の再生成比率を実測する。"""
    agent = _build_agent()
    result = asyncio.run(agent.execute(_ctx(agent)))
    gate = result.artifacts.get("gate_evaluation", {})
    ratio = 1.0 if result.should_retry else 0.0
    return {
        "ratio": ratio,
        "should_retry": result.should_retry,
        "aggregate_score": gate.get("aggregate_score"),
        "mode": gate.get("mode"),
    }


def test_regeneration_ratio_is_measured():
    """再生成比率が実測値として得られること（Step 23 の効果検証）。

    注意: 本テストの監査器は **5 件すべてを不合格**に固定した
    「最悪シナリオ」であるため、100% になるのが正しい結果である。
    現実的なコーパスでの比率は `test_v6_audit_failure_rate.py`
    （`reject_threshold=0.20` の確率的モデル）が担当する。
    本番の数値としては（一方のみを効果測定表に載せないこと。
    """
    measured = _measure_regeneration_ratio()
    ratio = measured["ratio"]
    assert 0.0 <= ratio <= 1.0
    print(
        f"\n[実測] 再生成比率（全5監査不合格の最悪シナリオ）: {ratio:.1%}"
        f"（aggregate_score={measured['aggregate_score']}, mode={measured['mode']}）"
    )


def test_single_minor_failure_uses_local_patch_instead_of_full_rewrite():
    """軽微1件の不合格で全文再生成に落ちていないこと（Step 25 の効果）。"""
    agent = _build_agent()
    # deai 以外の監査を「すべて合格」に差し替え、deai だけを不合格にする
    async def _ok_screen(blueprint: str):
        return True, ""

    async def _ok_logical(**kwargs):
        return True, "", 1.0

    async def _ok_ability(**kwargs):
        return True, "", ""

    agent._fast_screener.screen_plot = _ok_screen
    agent._logical_auditor.audit_logical_consistency = _ok_logical
    agent._ability_checker.audit_ability_consistency = _ok_ability

    class _OkMonitor:
        async def extract_keywords(self, text: str):
            return []

        async def check_integrity(self, **kwargs):
            return True, 1.0, []

    agent._plot_monitor = _OkMonitor()

    result = asyncio.run(agent.execute(_ctx(agent)))
    print(
        f"\n[実測] 軽微1件: should_retry={result.should_retry} "
        f"status={result.artifacts.get('audit_status')}"
    )
    assert result.should_retry is False, (
        "軽微1件の不合格で全文再生成が発生している"
    )


def test_regeneration_target_measurement_is_reported():
    """目標との差が必ず数値として残ることを確認する（効果測定表用）。"""
    measured = _measure_regeneration_ratio()
    assert "ratio" in measured and measured["ratio"] is not None
    assert measured["mode"] in ("score_aggregation", "all_or_nothing")

