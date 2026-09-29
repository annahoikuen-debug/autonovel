"""tests/contract/test_v6_audit_parallel_equivalence.py.

v6 / Step 22: 監査5件の ``asyncio.gather`` 並列化（Step 21）が
**判定結果を変えない**ことを証明する契約テスト。

並列化で壊れてよいのは速度だけで、壊してはならないのは

1. 判定結果（合格／不合格・severity・学習調整）
2. ``audit_id`` 付きイベントの発火（発火順は変わるが欠けてはならない）
3. 例外隔離（1件の監査器の例外が他を止めない）
4. レイテンシ（並列が直列を下回る）

の4点である。1〜3 は常時検証、4 は CI 負荷を避けるため
``ANONYMIZED`` な負荷設定で無効化できる（``--run-latency`` で明示実行）。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.audit_agent import (  # noqa: E402
    CORE_AUDIT_CRITERIA,
    AuditAgent,
)

#: 各監査器の模擬レイテンシ（秒）。直列なら加算、並列なら最大値になる。
AUDIT_LATENCY = 0.05

#: レイテンシ計測は CI で不安定になりうるため、明示指定時のみ実行する。
RUN_LATENCY = os.environ.get("RUN_LATENCY_TESTS", "").lower() in ("1", "true", "yes", "on")

BLUEPRINT = "第1話 蓝图: カレンは王都で遺鍵を入手する。対立勢力が現れ、覚醒の瞬間が訪れる。"
DRAFTED = "王都の夜、カレンは静かに歩いた。遺鍵を握りしめたままだった。"


class _SleepLLM:
    """一定時間 sleep してから合否を返す決定論的な LLM フェイク。"""

    def __init__(self, delay: float = AUDIT_LATENCY) -> None:
        self.delay = delay
        self.calls: list[str] = []

    async def generate_json(self, purpose: str = "", prompt: str = "", **kwargs: Any) -> dict:
        await asyncio.sleep(self.delay)
        self.calls.append(purpose or prompt)
        return {"metadata": {"is_valid": True, "is_consistent": True, "feedback": "OK"}}


class _FakePromptManager:
    """プロンプトを素通しで組み立てるだけのフェイク。"""

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


class _NoLearningService:
    async def should_skip_audit_type(self, audit_type: str, field_path: str | None = None):
        return False, 0.0


def _build_agent(llm: Any = None) -> AuditAgent:
    agent = AuditAgent(
        repo=None,
        llm=llm if llm is not None else _SleepLLM(),
        prompt_manager=_FakePromptManager(),
        audit_llm=None,
        unified_auditor=_UnifiedStub(),
    )
    agent._learning_service = _NoLearningService()
    agent._fast_screener.llm = agent.llm
    agent._logical_auditor.llm = agent.llm
    agent._logical_auditor.generate_json = agent.llm
    agent._deai_auditor.llm = agent.llm
    agent._ability_checker.llm = agent.llm
    return agent


class _UnifiedStub:
    """UnifiedAuditor の差し替え（LLM 呼び出しを伴わない）。"""

    async def audit(self, text: str, character_profiles: str = "", plot_spec: str = ""):
        return _UnifiedReport()


class _UnifiedReport:
    is_acceptable = True
    final_score = 88.0
    qualitative = None
    conflicts: list[Any] = []


def _writing_context() -> dict[str, Any]:
    return {
        "plot": {"detailed_blueprint": BLUEPRINT},
        "sharp_edges": [],
        "emotional_hook": None,
        "world_settings": "{}",
        "characters_json": "[]",
        "prev_ctx": "",
    }


async def _run(agent: AuditAgent, parallel: bool) -> tuple[list[dict[str, Any]], float]:
    return await agent.run_audit_phase(
        _writing_context(), DRAFTED, book_id=1, ep_num=1, parallel=parallel
    )


def _comparable(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """比較用の射影（実行時間など非決定的な値を除く）。"""
    return [
        {
            "audit_id": o["audit_id"],
            "passed": o["passed"],
            "feedback": o["feedback"],
            "severity": o["severity"],
            "effective_severity": o["effective_severity"],
            "learning_adjusted": o["learning_adjusted"],
            "confidence_adjustment": o["confidence_adjustment"],
            "score": o["score"],
            "error": o["error"],
        }
        for o in outcomes
    ]


# ---------------------------------------------------------------------------
# テスト1: 判定結果の完全一致
# ---------------------------------------------------------------------------


def test_parallel_and_serial_audit_results_identical() -> None:
    """同一入力に対し、直列実行と並列実行の判定結果が完全一致すること。"""

    async def _scenario() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        serial_agent = _build_agent()
        parallel_agent = _build_agent()
        serial_outcomes, _ = await _run(serial_agent, parallel=False)
        parallel_outcomes, _ = await _run(parallel_agent, parallel=True)
        return _comparable(serial_outcomes), _comparable(parallel_outcomes)

    serial, parallel = asyncio.run(_scenario())

    assert [s["audit_id"] for s in serial] == [c.audit_id for c in CORE_AUDIT_CRITERIA] + [
        "unified_qualitative"
    ], "監査IDの並びが CORE_AUDIT_CRITERIA と一致していない"
    assert serial == parallel, (
        "並列化で判定結果が変わった:\n"
        f"serial  ={serial}\n"
        f"parallel={parallel}"
    )


# ---------------------------------------------------------------------------
# テスト2: audit_id 付きイベントが全件発火する
# ---------------------------------------------------------------------------


def test_audit_events_all_emitted() -> None:
    """5件すべての ``audit_id`` 付きイベントが発火すること（順序は問わない）。"""

    agent = _build_agent()
    asyncio.run(_run(agent, parallel=True))
    events = agent.drain_events()

    started = {e["audit_id"] for e in events if e["event"] == "audit.audit.started"}
    completed = {e["audit_id"] for e in events if e["event"] == "audit.audit.completed"}
    expected = {c.audit_id for c in CORE_AUDIT_CRITERIA}

    assert expected <= started, f"started イベントが不足: {expected - started}"
    assert expected <= completed, f"completed イベントが不足: {expected - completed}"
    assert all(
        "audit_id" in e
        for e in events
        if e["event"].startswith("audit.audit.") and e["event"] != "audit.audit.phase_completed"
    ), "audit_id を持たない監査イベントがある"

    phase = [e for e in events if e["event"] == "audit.audit.phase_completed"]
    assert len(phase) == 1, "phase_completed が 1 回だけ発火していない"
    assert set(phase[0]["audit_ids"]) == expected | {"unified_qualitative"}


# ---------------------------------------------------------------------------
# テスト3: 1件の例外が他を止めない
# ---------------------------------------------------------------------------


def test_one_auditor_exception_does_not_block_others() -> None:
    """1つの監査器が例外を投げても他の監査の結果が得られること。"""

    class _ExplodingScreener:
        async def screen_plot(self, blueprint: str) -> tuple[bool, str]:
            raise RuntimeError("boom")

    agent = _build_agent()
    agent._fast_screener = _ExplodingScreener()

    outcomes, _elapsed = asyncio.run(_run(agent, parallel=True))
    by_id = {o["audit_id"]: o for o in outcomes}

    exploding = by_id["fast_screen"]
    assert exploding["passed"] is False, "例外した監査が合格扱いになっている"
    assert exploding["error"] == "auditor_exception:RuntimeError", (
        f"例外理由が記録されていない: {exploding['error']}"
    )
    assert exploding["effective_severity"] == "critical", "例外が critical として扱われていない"

    for criterion in CORE_AUDIT_CRITERIA:
        if criterion.audit_id == "fast_screen":
            continue
        assert criterion.audit_id in by_id, f"{criterion.audit_id} の結果が無い"
        assert by_id[criterion.audit_id]["passed"] is True, (
            f"{criterion.audit_id} まで巻き込まれた"
        )

    # 1件例外でもゲートは他監査の結果で評価できる
    gate = agent.evaluate_gate(outcomes)
    assert gate["aggregate_score"] < gate["threshold"]
    assert gate["requires_regeneration"] is True


# ---------------------------------------------------------------------------
# テスト4: レイテンシ改善（CI では任意実行）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not RUN_LATENCY, reason="レイテンシ計測は RUN_LATENCY_TESTS=1 で有効化")
def test_audit_latency_is_reduced() -> None:
    """監査フェーズのレイテンシが直列時を下回ること。"""

    async def _measure(parallel: bool) -> float:
        agent = _build_agent()
        started = time.perf_counter()
        _outcomes, elapsed = await _run(agent, parallel=parallel)
        wall = time.perf_counter() - started
        assert elapsed > 0.0
        return wall

    serial = asyncio.run(_measure(False))
    parallel = asyncio.run(_measure(True))
    print(f"\n[実測] 監査フェーズ 直列={serial:.4f}s 並列={parallel:.4f}s")
    assert parallel < serial, (
        f"並列化してもレイテンシが短縮されていない（直列 {serial:.4f}s / 並列 {parallel:.4f}s）"
    )
