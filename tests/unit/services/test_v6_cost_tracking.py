"""tests/unit/services/test_v6_cost_tracking.py.

v5.3 / Step 2-3: 本番スキル経路への TokenTracker 注入と、
タスク種別ごとの LLM 呼び出し回数・トークン・コスト計測の検証。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.services.llm.tracked_adapter import (  # noqa: E402
    TrackedLLMAdapter,
    build_tracked_adapters,
)
from src.services.token_tracker import TokenTracker  # noqa: E402


class _FakeAdapter:
    """最小の LLM アダプタ（計測ロジックの検証用）"""

    def __init__(self, response: str = "生成結果") -> None:
        self.response = response
        self.model_name = "gemini-2.0-flash"
        self.calls: list[dict[str, Any]] = []

    async def generate_text(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.response

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.response

    async def stream_text(self, prompt: str, **kwargs: Any):
        self.calls.append({"prompt": prompt, **kwargs})
        for chunk in ("あ", "い", "う"):
            yield chunk

    def cancel(self) -> None:
        self.cancelled = True  # type: ignore[attr-defined]


class _FailingStreamAdapter(_FakeAdapter):
    """1 チャンク目だけ返してから例外を投げるストリーム。"""

    async def stream_text(self, prompt: str, **kwargs: Any):
        yield "あ"
        raise RuntimeError("upstream failure")


class TestTokenTrackerTaskBreakdown:
    def test_add_usage_without_task_type_keeps_legacy_behavior(self) -> None:
        """後方互換: task_type 省略時は従来の集計のみ。"""
        tracker = TokenTracker()
        tracker.add_usage(100, 50, ep_num=1, model_name="gemini-2.0-flash")
        assert tracker.total_tokens == 150
        assert tracker.usage_by_task == {}
        assert tracker.call_count_by_task == {}

    def test_task_type_records_call_count(self) -> None:
        tracker = TokenTracker()
        for _ in range(3):
            tracker.add_usage(10, 5, task_type="audit", model_name="gemini-2.0-flash")
        assert tracker.call_count_by_task["audit"] == 3
        assert tracker.usage_by_task["audit"]["total_tokens"] == 45

    def test_task_breakdown_shape(self) -> None:
        tracker = TokenTracker()
        tracker.add_usage(1000, 500, task_type="writing", model_name="claude-3-5-sonnet")
        tracker.add_usage(100, 0, task_type="audit", model_name="gemini-2.0-flash")
        breakdown = tracker.get_task_breakdown()
        assert set(breakdown) == {"writing", "audit"}
        assert breakdown["writing"]["calls"] == 1
        assert breakdown["writing"]["input_tokens"] == 1000
        assert breakdown["writing"]["output_tokens"] == 500
        assert breakdown["writing"]["models"]["claude-3-5-sonnet"]["calls"] == 1

    def test_cost_is_computed_per_task(self) -> None:
        """MODEL_PRICING に基づく推定コストがタスク별로加算される。"""
        tracker = TokenTracker()
        # gemini-2.0-flash: input 0.10 / output 0.40 (per 1M)
        tracker.add_usage(1_000_000, 1_000_000, task_type="audit", model_name="gemini-2.0-flash")
        cost = tracker.usage_by_task["audit"]["cost_usd"]
        assert cost == pytest.approx(0.50, abs=1e-6), f"unexpected cost: {cost}"
        assert tracker.get_total_cost_usd() == pytest.approx(0.50, abs=1e-6)

    def test_unknown_model_cost_is_zero(self) -> None:
        tracker = TokenTracker()
        tracker.add_usage(1000, 1000, task_type="audit", model_name="unknown-model-x")
        assert tracker.usage_by_task["audit"]["cost_usd"] == 0.0

    def test_cost_is_zero_without_model_name(self) -> None:
        tracker = TokenTracker()
        tracker.add_usage(1000, 1000, task_type="audit")
        assert tracker.usage_by_task["audit"]["cost_usd"] == 0.0

    def test_reset_clears_task_breakdown(self) -> None:
        tracker = TokenTracker()
        tracker.add_usage(10, 10, task_type="audit", model_name="gemini-2.0-flash")
        tracker.reset()
        assert tracker.usage_by_task == {}
        assert tracker.call_count_by_task == {}
        assert tracker.get_total_cost_usd() == 0.0


class TestTrackedLLMAdapter:
    @pytest.mark.asyncio
    async def test_generate_text_passes_through_and_records(self) -> None:
        inner = _FakeAdapter("本文が生成された")
        tracker = TokenTracker()
        adapter = TrackedLLMAdapter(inner, tracker, "writing", "gemini-2.0-flash")

        result = await adapter.generate_text("プロンプト", max_tokens=100)

        assert result == "本文が生成された", "応答が素通しされていない"
        assert inner.calls[0]["max_tokens"] == 100, "引数が素通しされていない"
        assert tracker.call_count_by_task["writing"] == 1
        assert tracker.usage_by_task["writing"]["output_tokens"] > 0

    @pytest.mark.asyncio
    async def test_sync_generate_is_awaited(self) -> None:
        """内側の `generate` が coroutine を返すケースにも対応する。"""
        inner = _FakeAdapter()
        tracker = TokenTracker()
        adapter = TrackedLLMAdapter(inner, tracker, "audit")
        assert await adapter.generate("プロンプト") == "生成結果"
        assert tracker.call_count_by_task["audit"] == 1

    @pytest.mark.asyncio
    async def test_stream_text_passes_chunks_and_records(self) -> None:
        inner = _FakeAdapter()
        tracker = TokenTracker()
        adapter = TrackedLLMAdapter(inner, tracker, "writing")
        chunks = [c async for c in adapter.stream_text("プロンプト")]
        assert chunks == ["あ", "い", "う"], "ストリームが素通しされていない"
        assert tracker.call_count_by_task["writing"] == 1

    @pytest.mark.asyncio
    async def test_stream_text_records_on_early_consumer_exit(self) -> None:
        """コンシューマーが途中で離脱しても、既消費分は必ず記録される。

        以前は `self._record(...)` が `async for` の後ろにしか無く、
        早期終了や上流例外だと課金済みトークンがローカルに記録されないまま
        消えていた（`generate_text` と挙動も不揃いだった）。

        `async for` の `break` だけでは async generator の終了が確定しないため、
        離脱として明確な `aclose()` を呼んでから検証する。
        """
        inner = _FakeAdapter()
        tracker = TokenTracker()
        adapter = TrackedLLMAdapter(inner, tracker, "writing")

        agen = adapter.stream_text("プロンプト")
        async for chunk in agen:
            if chunk == "い":
                break
        await agen.aclose()

        assert tracker.call_count_by_task["writing"] == 1, "早期終了でも計測が記録される"
        # 消費できたのは "あ" と "い" の 2 文字ぶん
        assert tracker.usage_by_task["writing"]["output_tokens"] == 2

    @pytest.mark.asyncio
    async def test_stream_text_records_when_upstream_raises(self) -> None:
        """上流例外時も、配信済みのトークンは記録される。"""
        inner = _FailingStreamAdapter()
        tracker = TokenTracker()
        adapter = TrackedLLMAdapter(inner, tracker, "writing")

        received = []
        with pytest.raises(RuntimeError):
            async for chunk in adapter.stream_text("プロンプト"):
                received.append(chunk)

        assert received == ["あ"]
        assert tracker.call_count_by_task["writing"] == 1
        # 配信できた 1 文字ぶんだけが記録される
        assert tracker.usage_by_task["writing"]["output_tokens"] == 1

    @pytest.mark.asyncio
    async def test_stream_text_includes_system_prompt_in_estimate(self) -> None:
        """stream_text も generate_text と同じく system_prompt を入力計測に含める。"""
        tracker = TokenTracker()
        adapter = TrackedLLMAdapter(_FakeAdapter(), tracker, "writing")

        with_system = [c async for c in adapter.stream_text("短い", system_prompt="SYS" * 50)]
        assert with_system == ["あ", "い", "う"]
        with_system_tokens = tracker.usage_by_task["writing"]["input_tokens"]

        tracker.reset()
        without_system = [c async for c in adapter.stream_text("短い")]
        assert without_system == ["あ", "い", "う"]
        without_system_tokens = tracker.usage_by_task["writing"]["input_tokens"]

        assert with_system_tokens > without_system_tokens, (
            "system_prompt が stream_text の計測に含まれていない"
        )

    def test_unknown_attributes_are_delegated(self) -> None:
        """既存スキルがアダプタ固有メソッドを呼んでも壊れないこと。"""
        inner = _FakeAdapter()
        inner.some_custom_method = MagicMock(return_value="ok")
        adapter = TrackedLLMAdapter(inner, TokenTracker(), "writing")
        assert adapter.some_custom_method() == "ok"

    def test_model_name_falls_back_to_inner(self) -> None:
        inner = _FakeAdapter()
        adapter = TrackedLLMAdapter(inner, TokenTracker(), "writing")
        assert adapter.model_name == "gemini-2.0-flash"

    def test_cancel_is_delegated(self) -> None:
        inner = _FakeAdapter()
        adapter = TrackedLLMAdapter(inner, TokenTracker(), "writing")
        adapter.cancel()
        assert getattr(inner, "cancelled", False) is True

    def test_token_estimate_is_deterministic(self) -> None:
        a = TrackedLLMAdapter._estimate_tokens("日本語のテキスト")
        b = TrackedLLMAdapter._estimate_tokens("日本語のテキスト")
        assert a == b
        assert a == len("日本語のテキスト")


class TestBuildTrackedAdapters:
    def test_returns_all_required_keys(self) -> None:
        inner = _FakeAdapter()
        result = build_tracked_adapters(inner, models={"writing": "gemini-2.0-flash"})
        for key in ("llm", "planning_llm", "audit_llm", "token_tracker"):
            assert key in result, f"{key} が依存辞書に含まれない"

    def test_distinct_task_types_for_each_purpose(self) -> None:
        result = build_tracked_adapters(_FakeAdapter())
        assert result["llm"]._task_type == "writing"
        assert result["planning_llm"]._task_type == "planning"
        assert result["audit_llm"]._task_type == "audit"

    def test_falls_back_to_primary_adapter(self) -> None:
        inner = _FakeAdapter()
        result = build_tracked_adapters(inner)
        assert result["planning_llm"]._inner is inner
        assert result["audit_llm"]._inner is inner

    def test_shares_single_tracker(self) -> None:
        """全アダプタが同一トラッカーを共有すること（集約必須）。"""
        result = build_tracked_adapters(_FakeAdapter())
        tracker = result["token_tracker"]
        assert result["llm"]._tracker is tracker
        assert result["planning_llm"]._tracker is tracker
        assert result["audit_llm"]._tracker is tracker

    @pytest.mark.asyncio
    async def test_counts_are_aggregated_per_purpose(self) -> None:
        inner = _FakeAdapter()
        result = build_tracked_adapters(inner)
        await result["llm"].generate_text("本文生成プロンプト")
        await result["audit_llm"].generate_text("監査プロンプト")
        await result["audit_llm"].generate_text("監査プロンプト")

        breakdown = result["token_tracker"].get_task_breakdown()
        assert breakdown["writing"]["calls"] == 1
        assert breakdown["audit"]["calls"] == 2


class TestProductionInjection:
    def test_generation_tasks_uses_tracked_adapters(self) -> None:
        """`generation_tasks.py` が計測付きアダプタを注入すること（Step 2 完了判定）。"""
        source = (
            ROOT_DIR / "src" / "backend" / "tasks" / "generation_tasks.py"
        ).read_text("utf-8")
        assert "build_tracked_adapters" in source, (
            "generation_tasks.py が計測付きアダプタを注入していない"
        )
        assert '"token_tracker": tracked["token_tracker"]' in source, (
            "dependencies に token_tracker が含まれていない"
        )
        assert '"llm": tracked["llm"]' in source, (
            "dependencies の llm が計測付きになっていない"
        )
