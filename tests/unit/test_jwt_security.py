import pytest
from pydantic import ValidationError
from src.backend.config import Settings
from src.backend.security.jwt import create_access_token, create_refresh_token, decode_token

# テストプロセスには conftest が AUTH_DISABLED=true を設定している。
# そのままだと APP_ENV="production" の Settings が一斉に「本番で認証無効は不可」
# で ValidationError になり、検証したい JWT 鍵の検証に到達しない。
# またローカル .env も混ざらないよう _env_file=None を渡す。


def test_production_fails_fast_with_default_or_missing_secret():
    """本番環境でJWT_SECRET_KEYが未設定・デフォルトの場合に Settings の
    model_validator が起動阻止 ValidationError を送出することを検証"""
    # デフォルト（プレースホルダ）鍵 → ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=False,
            JWT_SECRET_KEY="autonovel-super-secret-key-32bytes-minimum-change-in-prod",
            DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
            _env_file=None,
        )

    # 空鍵 → ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=False,
            JWT_SECRET_KEY="",
            DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
            _env_file=None,
        )

    # 短すぎる鍵 → get_jwt_secret_key() 呼び出し時の ValueError (実装は起動時にのみ検証)
    short_settings = Settings(
        APP_ENV="production",
        AUTH_DISABLED=False,
        JWT_SECRET_KEY="short-key",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        _env_file=None,
    )
    with pytest.raises(ValueError):
        short_settings.get_jwt_secret_key()


def test_production_accepts_valid_strong_secret():
    """本番環境で十分な長さの安全な秘密鍵が設定されていれば正しく受理されることを検証"""
    strong_key = "a" * 32
    prod_settings = Settings(
        APP_ENV="production",
        AUTH_DISABLED=False,
        JWT_SECRET_KEY=strong_key,
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        _env_file=None,
    )
    assert prod_settings.get_jwt_secret_key() == strong_key


def test_jwt_token_generation_and_type_enforcement():
    """アクセストークンとリフレッシュトークンの発行および型検証

    create_access_token / create_refresh_token は data dict を受け取る。
    """
    token = create_access_token(data={"sub": "42", "role": "user"})
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["role"] == "user"
    assert payload["type"] == "access"

    # リフレッシュトークンをアクセストークンとして復号しようとすると None になる
    refresh_token = create_refresh_token(data={"sub": "42"})
    assert decode_token(refresh_token, expected_type="access") is None
    # 正しい型であれば復号できる
    refresh_payload = decode_token(refresh_token, expected_type="refresh")
    assert refresh_payload["sub"] == "42"
    assert refresh_payload["type"] == "refresh"
