"""config.py の本番環境バリデーション検証テスト

テストプロセスには conftest が AUTH_DISABLED=true を設定しているため、
各 Settings 構築で明示的に AUTH_DISABLED=False を渡す。
さもないと「本産で認証無効は不可」で先に落ちて、検証対象である
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
            _env_file=None,
        )


def test_development_allows_auth_disabled():
    """開発モードで AUTH_DISABLED=True は許容される。"""
    from src.backend.config import Settings
    settings = Settings(
        APP_ENV="development",
        AUTH_DISABLED=True,
        _env_file=None,
    )
    assert settings.APP_ENV == "development"
    assert settings.AUTH_DISABLED is True
