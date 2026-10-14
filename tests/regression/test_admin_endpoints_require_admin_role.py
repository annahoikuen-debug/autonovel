import pytest
from fastapi import HTTPException
from src.backend.auth import require_admin_user_or_key
from src.backend.database.models import User
from src.backend.config import settings


class DummyAsyncSession:
    pass


@pytest.mark.asyncio
async def test_admin_jwt_is_allowed(monkeypatch):
    """admin ロールの JWT は require_admin_user_or_key を通過すること。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)

    from src.backend.security.jwt import create_access_token
    token = create_access_token(data={"sub": "1", "role": "admin"})

    async def mock_get_current_user(token, db):
        return User(id=1, role="admin", email="admin@example.com", display_name="Admin")

    monkeypatch.setattr("src.backend.auth.get_current_user", mock_get_current_user)

    user = await require_admin_user_or_key(token=token, authorization="", db=DummyAsyncSession())
    assert user.role == "admin"


@pytest.mark.asyncio
async def test_regular_user_jwt_is_forbidden(monkeypatch):
    """一般 user ロールの JWT は require_admin_user_or_key で 403 となること。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)

    from src.backend.security.jwt import create_access_token
    token = create_access_token(data={"sub": "2", "role": "user"})

    async def mock_get_current_user(token, db):
        return User(id=2, role="user", email="user@example.com", display_name="User")

    monkeypatch.setattr("src.backend.auth.get_current_user", mock_get_current_user)

    with pytest.raises(HTTPException) as exc_info:
        await require_admin_user_or_key(token=token, authorization="", db=DummyAsyncSession())
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_valid_api_key_receives_api_readonly_role(monkeypatch):
    """有効な API キーで呼び出した場合、管理者権限には昇格せず api_readonly ロールとなること。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    monkeypatch.setattr(settings, "ALLOWED_API_KEYS", "secret-api-key")

    user = await require_admin_user_or_key(token="", authorization="Bearer secret-api-key", db=DummyAsyncSession())
    assert user.role == "api_readonly"
