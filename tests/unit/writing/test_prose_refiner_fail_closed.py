"""H8: `ProseRefinerAgent.refine` の fail-closed 検証。

LLM クライアントに `generate_text` / `generate` / `ainvoke` のいずれのメソッドも無い場合、
プロンプト文字列が本文に混入しないことを保証する（現行の fail-open 実装では赤となる）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from src.agents.writing.prose_refiner_agent import ProseRefinerAgent

DRAFT = "主人公は立ち止まった。その名を古代の魔導書と書く。"


class _NoMethodLLM:
    """generate_text / generate / ainvoke のいずれも持たない LLM スティブ。"""

    pass


class _NoAdapterLLMService:
    """adapter 属性も generate_text / generate も持たない LLMService ライクオブジェクト。"""

    adapter = None


async def test_llm_missing_methods_returns_original_without_prompt_leak():
    """LLM メソッド欠如時：refined_text == draft_text かつプロンプト先頭断片が混入しない。"""
    refiner = ProseRefinerAgent(llm_service=_NoMethodLLM())
    result = await refiner.refine(draft_text=DRAFT)

    assert result.refined_text == DRAFT, f"原文が破壊された: {result.refined_text!r}"
    assert result.total_fixes_count == 0
    # プロンプト先頭の固定断片が本文に混入していないこと
    assert "# スマートプロセ精製指示" not in result.refined_text
    assert "以下のテキストを、" not in result.refined_text


async def test_llm_service_no_adapter_no_methods_returns_original():
    """llm_service に adapter も generate_* も無い場合も原文を返す。"""
    refiner = ProseRefinerAgent(llm_service=_NoAdapterLLMService())
    result = await refiner.refine(draft_text=DRAFT)

    assert result.refined_text == DRAFT
    assert "# スマートプロセ精製指示" not in result.refined_text


async def test_empty_draft_returns_empty():
    """空入力は原文そのまま（空文字）。"""
    refiner = ProseRefinerAgent(llm_service=_NoMethodLLM())
    result = await refiner.refine(draft_text="")
    assert result.refined_text == ""
    assert result.total_fixes_count == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
