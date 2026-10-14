import pytest
from src.models.billing import PlanTier, TransactionType, CreateCheckoutRequest, CheckoutResponse, CreditBalanceResponse
from datetime import datetime

def test_plan_tier_values():
    assert PlanTier.FREE == "free"
    assert PlanTier.STARTER == "starter"
    assert PlanTier.PRO == "pro"
    assert PlanTier.ENTERPRISE == "enterprise"

def test_transaction_type_values():
    assert TransactionType.MONTHLY_GRANT == "monthly_grant"
    assert TransactionType.PACK_PURCHASE == "pack_purchase"
    assert TransactionType.CONSUMPTION == "consumption"
    assert TransactionType.REFUND == "refund"
    assert TransactionType.ADMIN_ADJUST == "admin_adjust"

def test_create_checkout_request():
    req = CreateCheckoutRequest(price_id="price_123", mode="payment")
    assert req.price_id == "price_123"
    assert req.mode == "payment"
    
    with pytest.raises(ValueError):
        CreateCheckoutRequest(price_id="price_123", mode="invalid")

def test_checkout_response():
    resp = CheckoutResponse(checkout_url="https://example.com")
    assert resp.checkout_url == "https://example.com"

def test_credit_balance_response():
    resp = CreditBalanceResponse(balance=100, plan_tier=PlanTier.FREE, current_period_end=datetime.now())
    assert resp.balance == 100
    assert resp.plan_tier == PlanTier.FREE
    assert isinstance(resp.current_period_end, datetime)
