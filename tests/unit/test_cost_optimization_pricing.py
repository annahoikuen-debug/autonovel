"""未知モデルの価格解決が黙って $0 にならないことの回帰テスト。

T6 Step 5 の回帰防止。

従来 `TokenTracker.estimate_cost_usd` は `MODEL_PRICING` に無いモデルに対して
**黙って 0.0** を返していた。モデルルーティング（`ENABLE_MODEL_ROUTING`）を
有効化すると、未知モデルへ切り替わった瞬間にコスト計測が=$0 として無言化し、
ルーティングの効果検証ができなくなる。
"""

import logging

import pytest

from src.config.cost_optimization import (
    MODEL_PRICING,
    UnknownModelPricingError,
    resolve_pricing,
)
from src.services.token_tracker import _WARNED_UNKNOWN_MODELS, TokenTracker

UNKNOWN = "totally-unknown-model-xyz"


# ── resolve_pricing の契約 ───────────────────────────────────────


def test_known_model_resolves():
    pricing = resolve_pricing("claude-3-5-haiku")
    assert pricing["input"] > 0
    assert pricing["output"] > 0


def test_unknown_model_raises_instead_of_zero():
    """未知モデルは例外を投げ、0 を返さないこと。"""
    with pytest.raises(UnknownModelPricingError):
        resolve_pricing(UNKNOWN)


def test_empty_model_raises():
    with pytest.raises(UnknownModelPricingError):
        resolve_pricing("")


def test_error_message_lists_registered_models():
    """エラーメッセージから登録済みモデルが分かること（運用時の発見性）。"""
    with pytest.raises(UnknownModelPricingError) as excinfo:
        resolve_pricing(UNKNOWN)
    assert "claude-3-5-haiku" in str(excinfo.value)
    assert UNKNOWN in str(excinfo.value)


# ── TokenTracker 側の後方互換挙動 ───────────────────────────────


@pytest.fixture(autouse=True)
def _clear_warned_models():
    _WARNED_UNKNOWN_MODELS.clear()
    yield
    _WARNED_UNKNOWN_MODELS.clear()


def test_known_model_cost_is_computed():
    cost = TokenTracker.estimate_cost_usd(1_000_000, 1_000_000, "claude-3-5-haiku")
    expected = MODEL_PRICING["claude-3-5-haiku"]["input"] + \
        MODEL_PRICING["claude-3-5-haiku"]["output"]
    assert cost == pytest.approx(expected)


def test_unknown_model_is_reported_by_tracker(caplog):
    """tracker は後方互換のため 0 を返すが、warning を1回出すこと。"""
    with caplog.at_level(logging.WARNING, logger="src.services.token_tracker"):
        cost = TokenTracker.estimate_cost_usd(1000, 500, UNKNOWN)

    assert cost == 0.0
    hits = [r for r in caplog.records if UNKNOWN in r.getMessage()]
    assert hits, (
        "未知モデルのコストが 0 のまま警告も出ない。"
        "ルーティングの効果が無言で計測不能になる"
    )


def test_unknown_model_warning_is_not_spammed(caplog):
    """同一モデルの警告は1度だけ（ログ floods 防止）。"""
    with caplog.at_level(logging.WARNING, logger="src.services.token_tracker"):
        for _ in range(5):
            TokenTracker.estimate_cost_usd(1000, 500, UNKNOWN)

    hits = [r for r in caplog.records if UNKNOWN in r.getMessage()]
    assert len(hits) == 1, f"警告が {len(hits)} 回出ている（1回であるべき）"


def test_no_model_name_stays_silent(caplog):
    """`model_name=None` は「情報不足」であって未知モデルではないため警告しない。"""
    with caplog.at_level(logging.WARNING, logger="src.services.token_tracker"):
        cost = TokenTracker.estimate_cost_usd(1000, 500, None)
    assert cost == 0.0
    assert not [r for r in caplog.records if "未知モデル" in r.getMessage()]
