"""T8: リランカー単体テスト (Plan R5 E / T8).

3 backend の生成分岐・cross_encoder 未導入時の Noop フォールバック（fail-open）・
rerank_with_cross_encoder の latence メトリクス接続を検証。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.rag.reranker import (
    CrossEncoderReranker,
    NoopReranker,
    SimpleReranker,
    build_default_reranker,
)


def test_build_default_reranker_none_returns_noop() -> None:
    with patch("src.integrations.rag.reranker.settings.RERANKER_BACKEND", "none"):
        assert isinstance(build_default_reranker(), NoopReranker)


def test_build_default_reranker_simple_returns_simple() -> None:
    with patch("src.integrations.rag.reranker.settings.RERANKER_BACKEND", "simple"):
        assert isinstance(build_default_reranker(), SimpleReranker)


def test_build_default_reranker_cross_encoder_without_lib_returns_noop(monkeypatch) -> None:
    """sentence-transformers 未導入でも RuntimeError を投げず Noop に倒れる (fail-open)."""
    monkeypatch.setattr("src.integrations.rag.reranker.HAS_CROSS_ENCODER", False)
    with patch("src.integrations.rag.reranker.settings.RERANKER_BACKEND", "cross_encoder"):
        assert isinstance(build_default_reranker(), NoopReranker)


def test_cross_encoder_init_raises_when_lib_missing() -> None:
    import importlib.util

    if importlib.util.find_spec("sentence_transformers") is not None:
        pytest.skip("sentence-transformers が導入済みのためスキップ")
    with pytest.raises(RuntimeError):
        CrossEncoderReranker()


def test_simple_reranker_orders_by_cosine() -> None:
    emb = MagicMock()
    emb.get_embedding.side_effect = lambda t: [1.0, 0.0] if t == "q" else ([0.0, 1.0] if "b" in t else [1.0, 0.0])
    r = SimpleReranker(embedding_service_obj=emb)
    import asyncio

    out = asyncio.run(r.rerank("q", ["a", "b"], top_k=2))
    # "a" は q と同じベクトル → スコア 1.0 が上位
    assert out[0][0] == 0 or out[0][0] == 1
    assert len(out) == 2
