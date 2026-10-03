from src.backend.security.jwt import create_access_token, create_refresh_token, decode_token
from src.backend.auth import validate_api_key_sync, _get_dev_mock_user

def test_jwt_create_and_decode():
    data = {"sub": "user_123", "role": "pro"}
    token = create_access_token(data)
    decoded = decode_token(token)
    assert decoded["sub"] == "user_123"
    assert decoded["role"] == "pro"
    assert "exp" in decoded

def test_jwt_refresh_token():
    data = {"sub": "user_456"}
    refresh_token = create_refresh_token(data)
    decoded = decode_token(refresh_token)
    assert decoded["sub"] == "user_456"

def test_jwt_tampered_token():
    data = {"sub": "user_admin"}
    token = create_access_token(data)
    tampered = token[:-4] + "xxxx"
    decoded = decode_token(tampered)
    assert decoded is None

def test_auth_validate_api_key(monkeypatch):
    """無効なキーは拒否されること。

    `validate_api_key_sync` は `settings.AUTH_DISABLED` が真のとき、検証Finite前に
    "dev-key" を返して認証をバイパスする（src/backend/auth.py:152-153）。
    tests/conftest.py は全テストで `AUTH_DISABLED=true` を設定するため、
    本来の検証経路を検証するには必ず認証を明示的に有効化する必要がある。
    """
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False)

    # 無効なキーの場合はFalseまたはNone
    assert validate_api_key_sync("invalid-key-999") is False

def test_auth_get_dev_mock_user():
    user = _get_dev_mock_user()
    assert "user_id" in user or "id" in user or "sub" in user or hasattr(user, "id")
