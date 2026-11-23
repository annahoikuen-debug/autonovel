"""Step 2（PLAN_T1）: Settings の repr にシークレット値が漏れないことを検証する。

``repr(settings)`` はログ出力・デバッグ出力経由で漏洩する可能性があるため、
シークレット系フィールドには ``repr=False`` を付与する。
本テストは「ダミー値が repr に現れないこと」を全シークレットフィールドで検証し、
過剰マスクを防ぐため通常フィールドが repr に現れることも確認する。
"""

from __future__ import annotations

from src.infrastructure.config.settings import Settings

# Step 2 で repr=False を付与した 9 フィールド（ダミー値）
SECRET_KWARGS: dict[str, str] = {
    "OPENAI_API_KEY": "dummy-openai-key",
    "ANTHROPIC_API_KEY": "dummy-anthropic-key",
    "GEMINI_API_KEY": "dummy-gemini-key",
    "OPENROUTER_API_KEY": "dummy-openrouter-key",
    "DALL_E_API_KEY": "dummy-dalle-key",
    "STRIPE_SECRET_KEY": "sk_test_dummy_stripe",
    "STRIPE_WEBHOOK_SECRET": "whsec_dummy_webhook",
    "ALLOWED_API_KEYS": "dummy-api-key",
    "JWT_SECRET_KEY": "dummy-jwt-secret-key",
}


def _make_settings() -> Settings:
    """ダミーシークレットを注入した testing 環境の Settings を返す。"""
    return Settings(APP_ENV="testing", **SECRET_KWARGS)


def test_settings_repr_does_not_leak_secrets() -> None:
    settings = _make_settings()
    rendered = repr(settings)
    for name, value in SECRET_KWARGS.items():
        assert value not in rendered, f"{name} の値が repr に漏れています"


def test_settings_str_does_not_leak_secrets() -> None:
    """``str(settings)`` は BaseModel では repr に委譲されるため同様に検証する。"""
    settings = _make_settings()
    rendered = str(settings)
    for name, value in SECRET_KWARGS.items():
        assert value not in rendered, f"{name} の値が str に漏れています"


def test_non_secret_fields_remain_visible_in_repr() -> None:
    """過剰マスクの防止: シークレット以外の通常フィールドは repr に現れること。"""
    settings = _make_settings()
    rendered = repr(settings)
    # 秘密ではない通常フィールドの値が可視であること（マスクしすぎていない証拠）
    assert settings.APP_NAME in rendered
    assert "APP_ENV" in rendered
