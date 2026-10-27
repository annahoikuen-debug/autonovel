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


def _read_env_example_secret() -> str:
    """.env.example に実在する JWT_SECRET_KEY / SECRET_KEY の例示値を 1 つ返す。"""
    from src.backend.config import ROOT_DIR

    env_example = ROOT_DIR / ".env.example"
    assert env_example.exists(), ".env.example が存在しない"
    for line in env_example.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() in {"JWT_SECRET_KEY", "SECRET_KEY"}:
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    pytest.skip(".env.example に JWT_SECRET_KEY / SECRET_KEY の例示値がない")


def test_production_rejects_env_example_jwt_secret():
    """`.env.example` の例示値をそのまま使ったら本番起動を拒否する。

    `.env.example` は公開リポジトリに載っている（＝誰でも読める）ため、
    そのまま `JWT_SECRET_KEY` に流用されると管理者トークンを偽造できる。
    旧実装は「空 / change-in-prod を含む」値しか拒否しなかったため、
    例示値は本番設定として素通りしていた。
    """
    from src.backend.config import Settings

    example_secret = _read_env_example_secret()
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            APP_ENV="production",
            AUTH_DISABLED=False,
            JWT_SECRET_KEY=example_secret,
            DATABASE_URL="postgresql://test:test@localhost:5432/test",
            STRIPE_WEBHOOK_SECRET="whsec_test",
            _env_file=None,
        )


def test_production_get_jwt_secret_key_rejects_env_example_value():
    """``get_jwt_secret_key()`` 側でも同じ判定が効く（実際のキー取得経路）。"""
    from src.backend.config import Settings

    example_secret = _read_env_example_secret()
    # 検証の入口 (model_validator) を先に通り過ぎたいので development で構築してから切り替える
    s = Settings(
        APP_ENV="development",
        AUTH_DISABLED=False,
        JWT_SECRET_KEY=example_secret,
        _env_file=None,
    )
    s.APP_ENV = "production"
    with pytest.raises(ValueError, match="CRITICAL SECURITY RISK"):
        s.get_jwt_secret_key()
