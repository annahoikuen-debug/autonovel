"""config.py の本番環境バリデーション検証テスト

テストプロセスには conftest が AUTH_DISABLED=true を設定しているため、
各 Settings 構築で明示的に AUTH_DISABLED=False を渡す。
さもないと「本番で認証無効は不可」で先に落ちて、検証対象である
JWT 鍵 / SQLite の判定に到達しない。
またローカル .env の影響を受けないよう _env_file=None を渡す。
"""
import pytest
from pydantic import ValidationError


def test_production_rejects_auth_disabled():
    from src.backend.config import Settings
    with pytest.raises(ValidationError, match="AUTH_DISABLED"):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=True,
            JWT_SECRET_KEY="a" * 64,
            DATABASE_URL="postgresql://test:test@localhost:5432/test",
            _env_file=None,
        )


def test_production_rejects_weak_jwt():
    from src.backend.config import Settings
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=False,
            JWT_SECRET_KEY="change-in-prod",
            DATABASE_URL="postgresql://test:test@localhost:5432/test",
            _env_file=None,
        )


def test_production_rejects_sqlite():
    from src.backend.config import Settings
    with pytest.raises(ValidationError, match="SQLite"):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=False,
            JWT_SECRET_KEY="a" * 64,
            DATABASE_URL="sqlite:///test.db",
            _env_file=None,
        )


def test_development_allows_defaults():
    from src.backend.config import Settings
    s = Settings(APP_ENV="development", _env_file=None)
    assert s.APP_ENV == "development"
