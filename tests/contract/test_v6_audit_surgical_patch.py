"""span パッチが Gate より先に効くとともに、既存 patch 戦略を潰さないことの回帰テスト。

W4 Step 8（``src/agents/audit_agent.py::try_local_patch``）の契約テスト。

計画書からの逸脱（理由付き）:

- ``test_existing_safe_replace_still_wins`` は ``current_value`` と
  ``suggested_value`` を同一値にした stub を使っていたが、
  ``_build_safe_replacer_mappings`` は ``current != suggested`` のときしか
  置換表を作らないため、そのままでは ``safe_replace`` に到達しなかった。
  実コードに合わせて異なる値へ修正した。
- span パッチは実際に LLM を呼ぶため、``MagicMock``（戻り値が文字列ではない）
  では ``SpanPatchApplier.validate`` を素通りできない。
  検証を通る「1段落ぶんの書き直し」を返すスタブ LLM を使うようにした。
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

import pytest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.audit_agent import (  # noqa: E402
    AuditAgent,
    is_async_polish_enabled,
    is_span_patch_enabled,
)

TEXT = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"


class _RewritingLLM:
    """``polish_span`` が 1 段落を書き直す LLM スタブ。

    差し替え結果が元の段落と同じ長さ・同じ段落数になるようにして、
    ``SpanPatchApplier.validate`` を素通りできる（= 本物の採用経路）ことを保証する。
    """

    def __init__(self, replacement: str) -> None:
        self.replacement = replacement
        self.calls: list[str] = []

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append(prompt)
        return self.replacement


class _Qualitative:
    def __init__(self, actionable_patch: str | None) -> None:
        self.critique = "AI感がある"
        self.actionable_patch = actionable_patch


class _Conflict:
    def __init__(self, current_value: str, suggested_value: str) -> None:
        self.current_value = current_value
        self.suggested_value = suggested_value


class _Report:
    is_acceptable = False
    final_score = 45.0

    def __init__(self, conflicts: list[Any] | None = None, actionable: str | None = None) -> None:
        self.conflicts = conflicts or []
        self.qualitative = _Qualitative(actionable)


def test_new_flags_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_AUDIT_SPAN_PATCH", raising=False)
    monkeypatch.delenv("ENABLE_AUDIT_POLISH_ASYNC", raising=False)
    assert is_span_patch_enabled() is True
    assert is_async_polish_enabled() is True


def test_new_flags_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "0")
    assert is_span_patch_enabled() is False


async def test_span_polish_preferred_over_actionable_append(monkeypatch: pytest.MonkeyPatch) -> None:
    """actionable_patch がある場合でも span パッチが優先されること。"""
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "1")
    agent = AuditAgent()
    agent._audit_llm = _RewritingLLM("その名を古代の魔道書と記す。")
    report = _Report(actionable="追記すべき文章")

    out = await agent.try_local_patch(
        TEXT,
        unified_report=report,
        failed_outcomes=[
            {
                "audit_id": "deai",
                "severity": "medium",
                "error": None,
                "feedback": "古代の魔導書",
            }
        ],
    )

    assert out is not None, f"span パッチが成立していない: {agent.drain_events()}"
    assert out["strategy"] == "span_polish"
    assert "追記すべき文章" not in out["text"]
    assert out["text"] != TEXT, "本文が書き換わっていない"
    assert out["replacements"] == 1
    assert out["triage_level"] == "span"
    assert isinstance(out["paragraph_index"], int)


async def test_existing_safe_replace_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """既存の SafeReplacer 経路が壊れていないこと（span より先に評価される）。"""
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "1")
    agent = AuditAgent()
    agent._audit_llm = None
    report = _Report(
        conflicts=[_Conflict(current_value="MAGIC", suggested_value="MAGICITE")],
        actionable="後付けの文章",
    )

    out = await agent.try_local_patch(
        "MAGIC が光った。", unified_report=report, failed_outcomes=[]
    )

    assert out is not None and out["strategy"] == "safe_replace"
    assert out["text"] == "MAGICITE が光った。"


async def test_span_patch_disabled_returns_none_like_before(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "0")
    agent = AuditAgent()
    agent._audit_llm = _RewritingLLM("その名を古代の魔道書と記す。")

    out = await agent.try_local_patch(
        TEXT,
        unified_report=None,
        failed_outcomes=[
            {"audit_id": "deai", "severity": "medium", "error": None, "feedback": "古代の魔導書"}
        ],
    )
    assert out is None


async def test_span_patch_disabled_falls_back_to_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    """span を OFF にすると、修正前の挙動（actionable_patch 追記）へ戻る。"""
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "0")
    agent = AuditAgent()
    agent._audit_llm = _RewritingLLM("その名を古代の魔道書と記す。")
    report = _Report(actionable="追記すべき文章")

    out = await agent.try_local_patch(
        TEXT,
        unified_report=report,
        failed_outcomes=[
            {"audit_id": "deai", "severity": "medium", "error": None, "feedback": "古代の魔導書"}
        ],
    )
    assert out is not None and out["strategy"] == "actionable_patch"
    assert out["text"].endswith("追記すべき文章")


async def test_failed_outcomes_defaults_to_none_for_backward_compatibility() -> None:
    """既存の呼び出し（failed_outcomes なし）が引数エラーにならないこと。"""
    agent = AuditAgent()
    agent._audit_llm = None
    out = await agent.try_local_patch("何もない。", None)
    assert out is None
