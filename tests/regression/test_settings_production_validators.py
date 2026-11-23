"""Step 3（PLAN_T1）: 本番環境の CORS_ORIGINS ワイルドカード拒否を検証する。

``Settings.validate_production_secrets`` は ``APP_ENV=production`` で
``CORS_ORIGINS`` に ``*`` が含まれる場合、起動時（Settings 構築時）に拒否する。
開発環境では ``*`` が許容されるが、資格情報付きクロスオリジンは無効化される
（``app_factory.py`` の縦深防御と同一挙動）。

注意: ``tests/conftest.py`` が ``AUTH_DISABLED=true`` を ``setdefault`` するため、
本番バリデータを通すテストでは認証チェック対象の環境変数をすべて明示的に上書きする。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.infrastructure.config.settings import Settings


def _production_kwargs() -> dict[str, str | bool]:
    """本番バリデータを通過する最低限の正しい本番設定を返す。

    conftest の環境変数（AUTH_DISABLED=true など）より init kwargs を優先させるため、
    バリデータが検査するフィールドはすべて明示する。
    """
    return {
        "APP_ENV": "production",
        # 本番では認証バイパス禁止（conftest の setdefault("AUTH_DISABLED", "true") を上書き）
        "AUTH_DISABLED": False,
        # 32 バイト以上・不安全リスト外の鍵
        "JWT_SECRET_KEY": "a" * 40,
        # SQLite 以外の DB
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/autonovel",
        # 未署名 webhook の許可は本番拒否対象なので明示 False
        "ALLOW_UNSIGNED_WEBHOOKS": False,
        # 本番必須の Stripe Webhook シークレット
        "STRIPE_WEBHOOK_SECRET": "whsec_valid_secret",
        # ヘッダーワイルドカードも本番拒否対象なので明示
        "CORS_ALLOW_HEADERS": "Content-Type,Authorization",
        # 実オリジンの明示列挙
        "CORS_ORIGINS": "https://example.com",
    }


def test_production_rejects_cors_origins_wildcard() -> None:
    """本番 + CORS_ORIGINS='*' は ValidationError（ValueError 由来）で拒否される。"""
    kwargs = _production_kwargs()
    kwargs["CORS_ORIGINS"] = "*"
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_production_accepts_explicit_origins() -> None:
    """本番 + 実オリジン列挙は構築でき、資格情報付きアクセスも許可される。"""
    settings = Settings(**_production_kwargs())  # type: ignore[arg-type]
    assert settings.APP_ENV == "production"
    assert settings.cors_allow_credentials is True


def test_development_allows_wildcard_but_disables_credentials() -> None:
    """開発環境 + '*' は許容されるが、資格情報付きクロスオリジンは無効化される。"""
    settings = Settings(APP_ENV="development", CORS_ORIGINS="*")
    assert settings.cors_allow_credentials is False


def test_development_explicit_origins_keep_credentials_enabled() -> None:
    """開発環境 + 実オリジン列挙では資格情報付きアクセスが有効のまま。"""
    settings = Settings(APP_ENV="development", CORS_ORIGINS="https://example.com")
    assert settings.cors_allow_credentials is True
