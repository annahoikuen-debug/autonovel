"""src/models/billing.py, context.py, visual_key_scene.py の単体テスト."""
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.billing import (
    CheckoutResponse,
    CreateCheckoutRequest,
    CreditBalanceResponse,
    PlanTier,
    TransactionType,
)
from src.models.context import ImmutableInput, RunState, SystemSettings
from src.models.visual_key_scene import VisualKeyScene


class TestPlanTier:
    def test_values(self):
        assert PlanTier.FREE.value == "free"
        assert PlanTier.STARTER.value == "starter"
        assert PlanTier.PRO.value == "pro"
        assert PlanTier.ENTERPRISE.value == "enterprise"


class TestTransactionType:
    def test_values(self):
        assert {t.value for t in TransactionType} == {
            "monthly_grant", "pack_purchase", "consumption", "refund", "admin_adjust",
        }


class TestCreateCheckoutRequest:
    def test_defaults(self):
        r = CreateCheckoutRequest(price_id="price_pro")
        assert r.mode == "subscription"

    def test_payment_mode(self):
        r = CreateCheckoutRequest(price_id="p", mode="payment")
        assert r.mode == "payment"

    def test_invalid_mode(self):
        with pytest.raises(ValidationError):
            CreateCheckoutRequest(price_id="p", mode="weird")

    def test_missing_price_id(self):
        with pytest.raises(ValidationError):
            CreateCheckoutRequest()


class TestResponses:
    def test_checkout_response(self):
        assert CheckoutResponse(checkout_url="https://x").checkout_url == "https://x"

    def test_credit_balance(self):
        r = CreditBalanceResponse(balance=10, plan_tier=PlanTier.PRO)
        assert r.current_period_end is None
        assert r.plan_tier is PlanTier.PRO

    def test_credit_balance_with_period_end(self):
        now = datetime(2030, 1, 1)
        r = CreditBalanceResponse(balance=1, plan_tier=PlanTier.FREE, current_period_end=now)
        assert r.current_period_end == now


class TestContextModels:
    def test_immutable_input(self):
        m = ImmutableInput(book_id=1, genre="fantasy", initial_concept={"a": 1})
        assert m.book_id == 1 and m.initial_concept == {"a": 1}

    def test_immutable_input_missing_field(self):
        with pytest.raises(ValidationError):
            ImmutableInput(book_id=1, genre="fantasy")

    def test_system_settings_defaults(self):
        s = SystemSettings(model_writing="gpt", model_planning="gpt")
        assert s.max_history_len == 30
        assert s.safe_append_mode == "auto"

    def test_run_state_defaults(self):
        r = RunState(current_episode=1)
        assert r.context_data == {}
        assert r.history == []


def test_visual_key_scene():
    v = VisualKeyScene(scene_id=2, description="夜空", importance="high")
    assert v.scene_id == 2 and v.importance == "high"


def test_visual_key_scene_invalid():
    with pytest.raises(ValidationError):
        VisualKeyScene(scene_id=2, description="夜空")
