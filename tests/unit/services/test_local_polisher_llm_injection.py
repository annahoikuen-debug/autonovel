"""LocalPolisher が注入 LLM を使い、グローバル関数を呼ばないことの回帰テスト。

T6 Step 7 の回帰防止。

旧実装は `LocalPolisher.polish()` がモジュールグローバル `call_llm_api` を
直接呼ぶ同期メソッドで、`audit_agent.py` は `await` せずにそれpirationいた。
結果として、この経路の LLM 呼出は
`tracked_adapter`（token/cost 計測付き）を**完全にバイパス**していた
= コスト計測に一切乗らない LLM 呼出。
"""

import inspect

import pytest

import src.generation.local_polish as mod
from src.generation.local_polish import LocalPolisher

TEXT = "前置き。改善対象の文がここにある。後書き。"
TARGET = "改善対象の文がここにある。"


class _AsyncLLM:
    def __init__(self, out: str = "推敲された文。") -> None:
        self.out = out
        self.calls = 0

    async def generate_text(self, prompt, **kwargs):
        self.calls += 1
        self.last_prompt = prompt
        return self.out


class _SyncLLM:
    def __init__(self, out: str = "推敲された文。") -> None:
        self.out = out
        self.calls = 0

    def generate_text(self, prompt, **kwargs):
        self.calls += 1
        return self.out


def _start() -> int:
    return TEXT.index(TARGET)


# ── 注入 LLM 経路 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polish_with_llm_uses_injected_llm(monkeypatch):
    """注入 LLM が使われ、グローバル `call_llm_api` は呼ばれないこと。"""
    called = {"global": 0}

    def _boom(*a, **k):
        called["global"] += 1
        raise AssertionError("グローバル call_llm_api が呼ばれた（計測バイパス）")

    monkeypatch.setattr(mod, "call_llm_api", _boom)

    llm = _AsyncLLM()
    out = await LocalPolisher().polish_with_llm(TEXT, (_start(), _start() + len(TARGET)), "改善して", llm)

    assert llm.calls == 1
    assert called["global"] == 0
    assert "推敲された文。" in out


@pytest.mark.asyncio
async def test_polish_with_llm_accepts_sync_llm():
    """同期 llm も受け付けること（adapter 実装の差異を吸収する）。"""
    llm = _SyncLLM()
    out = await LocalPolisher().polish_with_llm(TEXT, (_start(), _start() + len(TARGET)), "改善して", llm)
    assert llm.calls == 1
    assert "推敲された文。" in out


@pytest.mark.asyncio
async def test_audit_agent_passes_injected_llm(monkeypatch):
    """`AuditAgent.try_local_patch` が注入 llm を polisher へ渡すこと。

    Tier 3（LocalPolisher）へ到達させるため、Tier 1（SafeReplacer）が
    置換を作らないよう `current_value == suggested_value` にする。
    """
    from src.agents.audit_agent import AuditAgent

    seen: dict = {}

    async def _fake_polish_with_llm(self, text, rng, instruction, llm):
        seen["llm"] = llm
        seen["rng"] = rng
        return text + "【改善】"

    monkeypatch.setattr(LocalPolisher, "polish_with_llm", _fake_polish_with_llm)

    agent = AuditAgent(llm=None, repo=None, event_bus=None)
    agent._audit_llm = "SENTINEL_LLM"

    class _Conflict:
        # Tier 1 が置換を作らないようにする（= LocalPolisher まで落ちる）
        current_value = TARGET
        suggested_value = TARGET

    class _Report:
        conflicts = [_Conflict()]
        qualitative = None

    result = await agent.try_local_patch(TEXT, _Report())

    assert seen.get("llm") == "SENTINEL_LLM", (
        "注入 LLM が polisher へ渡っていない（計測バイパスが再発）。"
        f"到達した strategy: {result and result.get('strategy')}"
    )
    assert result is not None and result["strategy"] == "local_polish"


def test_try_local_patch_is_async():
    """`try_local_patch` が async であること（注入 llm の await に必要）。"""
    from src.agents.audit_agent import AuditAgent

    assert inspect.iscoroutinefunction(AuditAgent.try_local_patch), (
        "try_local_patch が同期のまま。注入 LLM を await できない"
    )


# ── 後方互換 ────────────────────────────────────────────────────


def test_legacy_polish_still_works(monkeypatch):
    """`polish()`（同期・グローバル版）は従来どおり動くこと。"""
    monkeypatch.setattr(mod, "call_llm_api", lambda prompt: "推敲された文。")
    out = LocalPolisher().polish(TEXT, (_start(), _start() + len(TARGET)), "改善して")
    assert "推敲された文。" in out


def test_legacy_polish_stays_sync():
    """既存呼び出しを壊さないため `polish()` は同期のまま。"""
    assert not inspect.iscoroutinefunction(LocalPolisher.polish)


# ── 境界条件 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_range_returns_original():
    llm = _AsyncLLM()
    for bad in ((-1, 5), (10, 5), (0, len(TEXT) + 100)):
        out = await LocalPolisher().polish_with_llm(TEXT, bad, "改善して", llm)
        assert out == TEXT
    assert llm.calls == 0, "無効な範囲でも LLM を呼んでいる（無駄なコスト）"


@pytest.mark.asyncio
async def test_empty_llm_output_keeps_original():
    """LLM が空文字を返しても原文を壊さないこと。"""
    llm = _AsyncLLM(out="   ")
    out = await LocalPolisher().polish_with_llm(TEXT, (_start(), _start() + len(TARGET)), "改善して", llm)
    assert out == TEXT


@pytest.mark.asyncio
async def test_preamble_is_stripped():
    """前置き行が除去され、本文だけが残ること。"""
    llm = _AsyncLLM(out="承知しました。\n推敲された文。")
    out = await LocalPolisher().polish_with_llm(
        TEXT, (_start(), _start() + len(TARGET)), "改善して", llm
    )
    assert "承知" not in out
    assert "推敲された文。" in out
    assert out.startswith("前置き。")
    assert out.endswith("後書き。")
