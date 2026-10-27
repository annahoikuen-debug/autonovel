import pytest
from pydantic import ValidationError
from src.backend.config import Settings
from src.backend.security.jwt import create_access_token, create_refresh_token, decode_token

# テストプロセスには conftest が AUTH_DISABLED=true を設定している。
# そのままだと APP_ENV="production" の Settings が一斉に「本番で認証無効は不可」
# で ValidationError になり、検証したい JWT 鍵の検証に到達しない。
# またローカル .env も混ざらないよう _env_file=None を渡す。
#
# 加えて本番バリデータには「STRIPE_WEBHOOK_SECRET 未設定は不可」という
# 独立した検査がある。JWT 鍵だけを検証したい本テストでは、本番起動に必要な
# 他の入力（Webhook 署名シークレット）を満たさせたうえで JWT 鍵の挙動を見る。
VALID_WEBHOOK_SECRET = "whsec_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


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
            STRIPE_WEBHOOK_SECRET=VALID_WEBHOOK_SECRET,
            _env_file=None,
        )

    # 空鍵 → ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=False,
            JWT_SECRET_KEY="",
            DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
            STRIPE_WEBHOOK_SECRET=VALID_WEBHOOK_SECRET,
            _env_file=None,
        )

    # 短すぎる鍵 → get_jwt_secret_key() 呼び出し時の ValueError (実装は起動時にのみ検証)
    short_settings = Settings(
        APP_ENV="production",
        AUTH_DISABLED=False,
        JWT_SECRET_KEY="short-key",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        STRIPE_WEBHOOK_SECRET=VALID_WEBHOOK_SECRET,
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
        STRIPE_WEBHOOK_SECRET=VALID_WEBHOOK_SECRET,
        _env_file=None,
    )
    assert prod_settings.get_jwt_secret_key() == strong_key


def test_production_requires_stripe_webhook_secret():
    """本番環境で STRIPE_WEBHOOK_SECRET も ALLOW_UNSIGNED_WEBHOOKS も
    未設定なら起動阻止 ValidationError となることを検証

    署名検証を省略したままだと、Webhook を偽装してクレジットを
    不正に付与できてしまうため、本番では Secret の設定が必須。
    """
    # JWT 鍵は十分強力だが、Webhook Secret 未設定が拒否理由になること
    with pytest.raises(ValidationError, match="STRIPE_WEBHOOK_SECRET"):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=False,
            JWT_SECRET_KEY="b" * 32,
            DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
            STRIPE_WEBHOOK_SECRET="",
            ALLOW_UNSIGNED_WEBHOOKS=False,
            _env_file=None,
        )

    # 明示的に署名検証の省略を許可した場合のみ通る
    allowed = Settings(
        APP_ENV="production",
        AUTH_DISABLED=False,
        JWT_SECRET_KEY="b" * 32,
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        STRIPE_WEBHOOK_SECRET="",
        ALLOW_UNSIGNED_WEBHOOKS=True,
        _env_file=None,
    )
    assert allowed.ALLOW_UNSIGNED_WEBHOOKS is True


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
