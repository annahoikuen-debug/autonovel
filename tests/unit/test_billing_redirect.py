"""Stripe Checkout / Portal のリダイレクト先 allowlist の単体テスト。"""
from __future__ import annotations

import pytest

from src.backend.config import settings
from src.backend.routers.billing import _safe_redirect_url


@pytest.fixture
def frontend_url(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://novel.example.com")
    return "https://novel.example.com"


def test_relative_path_is_joined_to_frontend(frontend_url):
    assert _safe_redirect_url("/billing/success", "/billing") == (
        "https://novel.example.com/billing/success"
    )


def test_same_origin_absolute_url_is_allowed(frontend_url):
    url = "https://novel.example.com/billing/success"
    assert _safe_redirect_url(url, "/billing") == url


@pytest.mark.parametrize(
    "candidate",
    [
        "https://evil.example/phish",
        "//evil.example/phish",
        "javascript:alert(1)",
        "http://novel.example.com.evil.example/",
    ],
)
def test_external_url_falls_back_to_default(frontend_url, candidate):
    assert _safe_redirect_url(candidate, "/billing") == "https://novel.example.com/billing"


def test_missing_value_uses_default(frontend_url):
    assert _safe_redirect_url(None, "/billing") == "https://novel.example.com/billing"
