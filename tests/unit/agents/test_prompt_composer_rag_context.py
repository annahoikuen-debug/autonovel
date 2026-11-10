"""PromptComposer._format_rag_context の単体テスト（Plan R5 B1 / T2）。

fail-open（入力が不正でも空文字・例外なし）、is_forbidden 除外、
スコア降順・top_k、max_chars 上限を検証する。
"""

from __future__ import annotations

from src.agents.prompt_composer import PromptComposer


def test_empty_or_none_returns_empty() -> None:
    assert PromptComposer._format_rag_context(None) == ""
    assert PromptComposer._format_rag_context([]) == ""
    assert PromptComposer._format_rag_context("not a list") == ""


def test_forbidden_documents_are_excluded() -> None:
    docs = [
        {"content": "forbidden lore", "score": 0.99, "metadata": {"is_forbidden": True}},
        {"content": "allowed fact", "score": 0.50, "metadata": {"is_forbidden": False}},
    ]
    out = PromptComposer._format_rag_context(docs, max_chars=1000, top_k=5)
    assert "forbidden lore" not in out
    assert "allowed fact" in out


def test_score_descending_order_and_top_k() -> None:
    docs = [
        {"content": "low", "score": 0.10},
        {"content": "high", "score": 0.90},
        {"content": "mid", "score": 0.50},
    ]
    out = PromptComposer._format_rag_context(docs, max_chars=1000, top_k=2)
    high_pos = out.find("high")
    mid_pos = out.find("mid")
    low_pos = out.find("low")
    assert high_pos != -1
    assert mid_pos != -1
    assert low_pos == -1, f"top_k=2 なのに low が含まれている: {out}"
    assert high_pos < mid_pos, f"スコア降順でない: {out}"


def test_max_chars_is_respected() -> None:
    docs = [{"content": "x" * 300, "score": 0.9} for _ in range(10)]
    out = PromptComposer._format_rag_context(docs, max_chars=200, top_k=10)
    assert len(out) <= 200, f"max_chars=200 を超過: {len(out)} 文字 -> {out!r}"


def test_malformed_items_are_skipped_without_exception() -> None:
    docs = [
        {"content": "good", "score": 0.90},
        None,
        {"score": 0.50},            # content なし
        {"content": "", "score": 0.80},  # 空 content
        "not a dict",
        {"content": "also good", "score": 0.70, "metadata": None},
    ]
    out = PromptComposer._format_rag_context(docs, max_chars=1000, top_k=5)
    assert "good" in out
    assert "also good" in out


def test_defaults_use_settings() -> None:
    """max_chars / top_k を省略すると settings の既定値を使うこと。"""
    from src.backend.config import settings

    docs = [
        {"content": "a", "score": 0.9},
        {"content": "b", "score": 0.8},
        {"content": "c", "score": 0.7},
        {"content": "d", "score": 0.6},
        {"content": "e", "score": 0.5},
        {"content": "f", "score": 0.4},
    ]
    out = PromptComposer._format_rag_context(docs)
    # top_k=5 の既定により f は含まれない
    assert "f" not in out
    assert len(out) <= settings.RAG_CONTEXT_MAX_CHARS
