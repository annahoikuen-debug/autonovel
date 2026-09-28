"""src/agents/context_builder.py (非推奨エイリアス) の単体テスト."""

from __future__ import annotations

import warnings

import pytest

from src.agents.context_builder import ContextBuilder
from src.agents.context_builder_agent import ContextBuilderAgent


def test_is_subclass_and_warns():
    assert issubclass(ContextBuilder, ContextBuilderAgent)
    with pytest.warns(DeprecationWarning, match="ContextBuilder is deprecated"):
        inst = ContextBuilder()
    assert isinstance(inst, ContextBuilderAgent)


def test_forwards_kwargs():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        inst = ContextBuilder(repo="R", llm="L", style_rag="S", rag_prefetch="P")
    assert inst.repo == "R"
    assert inst.llm == "L"
    assert inst.style_rag == "S"
    assert inst.rag_prefetch == "P"
