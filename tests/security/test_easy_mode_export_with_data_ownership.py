"""Step 1 (C1): POST /easy_mode/export-with-data の認証＋所有権検証。

C1: `easy_mode.py:633-710` は get_current_user / verify_book_ownership を欠き、
任意の book_id で他人の本（タイトル・ジャンル・本文）を上書き可。
修正後、両方を満たさないリクエストは拒否される。
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.backend.server import app

client = TestClient(app)


def _override_auth(is_owner: bool):
    """認証・所有権依存をモックに差し替える。DB は触らない。"""

    async def fake_get_current_user():
        user = MagicMock()
        user.id = 100 if is_owner else 200
        user.email = "owner@example.com" if is_owner else "victim@example.com"
        user.role = "user"
        user.status = "active"
        return user

    async def fake_verify(book_id, current_user):
        # 本人の book_id(=100) だけ通す、他は 403
        if not is_owner:
            from fastapi import HTTPException
            from starlette import status

            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    app.dependency_overrides[src_get_current_user] = fake_get_current_user
    app.dependency_overrides[src_verify_book_ownership] = fake_verify


def _clear_overrides():
    app.dependency_overrides.clear()


import src.backend.auth as auth_mod
import src.backend.security.owner_guard as guard_mod

src_get_current_user = auth_mod.get_current_user
src_verify_book_ownership = guard_mod.verify_book_ownership


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    _clear_overrides()


def test_export_with_data_rejects_unauthenticated_when_dependency_added():
    """C1: 修正後、認証依存が無ければ 401/403 を返す。
    現状（修正前）は依存がないためこのテストはスキップ相当（source 検査で補完）。
    """
    _override_auth(is_owner=False)
    resp = client.post(
        "/easy_mode/export-with-data",
        json={"book_id": 999, "title": "x", "genre": "x", "current_text": "x"},
    )
    # 修正前は 403 に到達しない（依存が無いため）。修正後は 403。
    assert resp.status_code in (401, 403)


def test_export_with_data_rejects_cross_tenant():
    """C1: 他人の book_id は所有権検証で 403。"""
    _override_auth(is_owner=False)
    resp = client.post(
        "/easy_mode/export-with-data",
        json={"book_id": 999, "title": "Hacked", "genre": "x", "current_text": "x"},
    )
    assert resp.status_code == 403


def test_endpoint_source_calls_verify_book_ownership():
    """C1: easy_mode.py の export_with_data_endpoint が verify_book_ownership を呼ぶ（source検査）。"""
    import inspect
    from src.backend.routers import easy_mode

    src = inspect.getsource(easy_mode.export_with_data_endpoint)
    assert "verify_book_ownership" in src, "export_with_data_endpoint に verify_book_ownership がない"
    assert "get_current_user" in src or "current_user" in src, "認証依存が無い"
