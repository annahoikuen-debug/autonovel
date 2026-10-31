"""AutoNovel アプリケーション設定モジュール。

Pydantic BaseSettings により環境変数のバリデーションと一元管理を行う。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# プロジェクトのルートディレクトリ
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = ROOT_DIR / "storage"

# storage ディレクトリが存在しない場合は自動作成
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# 開発用エフェメラルJWTキーのプロセス内キャッシュ
_ephemeral_dev_jwt_secret: str | None = None

# `.env.example` に記載されたシークレット値のキャッシュ
_example_secret_keys: frozenset[str] | None = None

# 既知の「本番で使ってはならない」JWT 署名鍵。
# validate_production_secrets (起動時) と get_jwt_secret_key (鍵取得時) の
# 両方で参照する共有集合。片方にしか置かないと、経路によって判定が食い違う。
_INSECURE_JWT_SECRETS: frozenset[str] = frozenset(
    {
        "",
        "autonovel-super-secret-key-32bytes-minimum-change-in-prod",
        "autonovel-dev-secret-key-minimum-32-bytes-long",
        "your-secret-key-here",
        "change-me",
        "change_me_generate_with_openssl_rand_hex_32",
        "secret",
    }
)

# 本番 (APP_ENV=production) で JWT 署名鍵に課す最小長（バイト）。
# 32 バイト以上ないとソーススロッフィングの耐性が確保できない。
_MIN_PROD_JWT_SECRET_LEN = 32


def _is_insecure_jwt_secret(key: str | None) -> bool:
    """渡された鍵が既知の不安全鍵（空・例示・プレースホルダ）かどうか判定する。"""
    if not key:
        return True
    return key in _INSECURE_JWT_SECRETS or key in _load_example_secret_keys()


def _load_example_secret_keys() -> frozenset[str]:
    """`.env.example` に書かれた `JWT_SECRET_KEY` / `SECRET_KEY` の値を収集する。

    `.env.example` をそのまま `.env` にコピーして `APP_ENV=production` を設定すると、
    公開リポジトリに載っている値がそのまま JWT 署名キーになりうる（管理者トークンの
    偽造が可能）。そのため、本番起動時の判定材料として一度だけ読み込む。
    """
    global _example_secret_keys
    if _example_secret_keys is not None:
        return _example_secret_keys

    keys: set[str] = set()
    try:
        env_example = ROOT_DIR / ".env.example"
        if env_example.exists():
            for line in env_example.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                name, _, value = stripped.partition("=")
                if name.strip() not in {"JWT_SECRET_KEY", "SECRET_KEY"}:
                    continue
                value = value.strip().strip('"').strip("'")
                if value:
                    keys.add(value)
    except OSError:
        # .env.example が読めない場合は「例示値なし」とみなす（起動を止めない）
        pass

    _example_secret_keys = frozenset(keys)
    return _example_secret_keys


def _get_package_version() -> str:
    """pyproject.toml からバージョンを動的取得する。"""
    try:
        pyproject_path = ROOT_DIR / "pyproject.toml"
        if pyproject_path.exists():
            import tomllib
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                ver = data.get("project", {}).get("version")
                if ver:
                    return str(ver)
        from importlib.metadata import version
        return version("autonovel")
    except Exception:
        return "unknown"


class Settings(BaseSettings):
    """アプリケーション設定クラス。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # サーバー基本設定
    APP_NAME: str = "AutoNovel"
    APP_VERSION: str = Field(default_factory=lambda: _get_package_version())
    APP_ENV: Literal["development", "production", "testing", "local", "staging"] = "development"
    PORT: int = 8200
    HOST: str = "0.0.0.0"

    # データベース設定
    DATABASE_URL: str = Field(default_factory=lambda: f"sqlite:///{STORAGE_DIR / 'autonovel.db'}")
    # Docker Compose が `${POSTGRES_*}` 置換のために `.env` から読む値。
    # アプリ本体は DATABASE_URL を使うが、`.env.example` をそのまま `.env` に
    # コピーしたときに `extra="forbid"` で起動が失敗しないようここで受け止める。
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = Field(default=None, repr=False)
    POSTGRES_DB: str | None = None

    # Redis/キュー設定
    HUEY_BACKEND: Literal["sqlite", "redis"] = "sqlite"
    HUEY_SQLITE_PATH: str = Field(default_factory=lambda: str(STORAGE_DIR / "huey.db"))
    REDIS_URL: str = "redis://localhost:6379/0"

    # 認証・セキュリティ設定
    AUTH_DISABLED: bool = False
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080"
    )
    # `X-Forwarded-For` を信頼してよいプロキシの CIDR（カンマ区切り）。
    # 未設定（既定）または空の場合はヘッダーを一切信用せず、
    # 直接接続の peer (`request.client.host`) をクライアント IP として扱う。
    TRUSTED_PROXY_CIDRS: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ALLOW_HEADERS: str = "Content-Type,Authorization,X-API-Key,Accept,Origin,X-Requested-With"
    ALLOWED_API_KEYS: str = ""
    JWT_SECRET_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("JWT_SECRET_KEY", "SECRET_KEY"),
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        """本番環境でデフォルト値や空シークレットが使用されるのを防止する。

        起動時点で fail-fast させるため、後段の get_jwt_secret_key() でも検証される
        既知の不安全鍵をここでも拒否する（経路間で判定が食い違うのを防ぐ）。
        """
        if self.APP_ENV == "production":
            if self.AUTH_DISABLED:
                raise ValueError("本番環境 (APP_ENV=production) では AUTH_DISABLED=True は許可されません。")
            # 既知の不安全鍵（空・例示値・プレースホルダ）は起動時に拒否する。
            if _is_insecure_jwt_secret(self.JWT_SECRET_KEY):
                raise ValueError(
                    "本番環境 (APP_ENV=production) では .env.example の例示値・"
                    "プレースホルダ・空の JWT_SECRET_KEY を使用できません。"
                    "`openssl rand -hex 32` で生成した 32 バイト以上の鍵を設定してください。"
                )
            # 「change-in-prod を含む」鍵は部分一致でも拒否する（設定し忘れた検知）。
            if self.JWT_SECRET_KEY and "change-in-prod" in self.JWT_SECRET_KEY:
                raise ValueError(
                    "本番環境 (APP_ENV=production) では 'change-in-prod' を含む "
                    "JWT_SECRET_KEY を使用できません。"
                )
            if self.JWT_SECRET_KEY and len(self.JWT_SECRET_KEY) < _MIN_PROD_JWT_SECRET_LEN:
                raise ValueError(
                    f"本番環境 (APP_ENV=production) では JWT_SECRET_KEY は "
                    f"{_MIN_PROD_JWT_SECRET_LEN} バイト以上必要です（現在 {len(self.JWT_SECRET_KEY)} バイト）。"
                )
            if "sqlite" in self.DATABASE_URL:
                raise ValueError("本番環境では SQLite ではなく PostgreSQL の設定が必要です。")
            # 本番では署名検証の省略 (ALLOW_UNSIGNED_WEBHOOKS) を一切許可しない。
            # 署名を検証しない Webhook は偽装されるとクレジットの不正付与に直結するため、
            # 「明示オプトイン」であっても本番起動を拒否する（ローカル検証専用フラグ）。
            if self.ALLOW_UNSIGNED_WEBHOOKS:
                raise ValueError(
                    "本番環境 (APP_ENV=production) では ALLOW_UNSIGNED_WEBHOOKS=True は"
                    "許可されません。STRIPE_WEBHOOK_SECRET を設定し、署名検証を必須にしてください。"
                )
            if not self.STRIPE_WEBHOOK_SECRET:
                raise ValueError(
                    "本番環境 (APP_ENV=production) では STRIPE_WEBHOOK_SECRET の設定が必須です"
                    "（未設定のまま運用すると署名検証を省略できず、クレジットの偽装付与を受けます）。"
                )
            # CORS ヘッダー許可リストにワイルドカード `*` が含まれると、
            # 任意 Origin からのクロスサイトアクセスを許してしまう。
            if "*" in [h.strip() for h in self.CORS_ALLOW_HEADERS.split(",")]:
                raise ValueError(
                    "本番環境 (APP_ENV=production) では CORS_ALLOW_HEADERS にワイルドカード "
                    "`*` を指定できません。必要なヘッダー名を明示してください。"
                )
        return self

    # 外部決済設定
    # Stripe: 未設定は空文字 / None とし、Webhook 側は本地・テスト以外での
    # 未設定を致命エラーとして扱う（src/backend/routers/billing_webhook.py）。
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str = ""
    # 署名検証を完全に省略してよい環境向けオプトインフラグ（既定 False）。
    # ローカル検証以外で True にしないこと。
    ALLOW_UNSIGNED_WEBHOOKS: bool = False

    def get_jwt_secret_key(self) -> str:
        """JWTシークレットキーを取得し、本番環境での安全性を厳格に検証する。"""
        import os
        import logging
        key = self.JWT_SECRET_KEY or os.environ.get("JWT_SECRET_KEY") or os.environ.get("SECRET_KEY")
        if self.APP_ENV == "production":
            if _is_insecure_jwt_secret(key) or (key is not None and len(key) < _MIN_PROD_JWT_SECRET_LEN):
                raise ValueError(
                    "CRITICAL SECURITY RISK: In production, JWT_SECRET_KEY must be set to a secure string of at least 32 bytes. "
                    "Current key is missing, default, or too short."
                )
            return key  # type: ignore[return-value]

        # 開発・テスト環境
        if key and key not in _INSECURE_JWT_SECRETS:
            return key

        # 開発環境用フォールバック (固定文字列ではなくプロセス毎のエフェメラルキー)
        global _ephemeral_dev_jwt_secret
        if _ephemeral_dev_jwt_secret is None:
            import secrets
            _ephemeral_dev_jwt_secret = secrets.token_hex(32)
            logging.getLogger(__name__).warning(
                "[SECURITY WARNING] JWT_SECRET_KEY is not set or insecure. "
                "Generated an ephemeral development key for this process lifetime. "
                "Set a persistent JWT_SECRET_KEY in .env for production or persistent sessions."
            )
        return _ephemeral_dev_jwt_secret

    # ロギング設定
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console", "text"] = "console"

    # LLM設定 (5プロバイダ対応)
    # 実装済み: openai, gemini, mock, claude, ollama, vllm
    LLM_PROVIDER: Literal["openai", "gemini", "mock", "claude", "ollama", "vllm", "vertex"] = "mock"

    # OpenAI 互換設定
    OPENAI_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_KEY"),
    )
    OPENAI_BASE_URL: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Google Gemini 設定 (Step 37)
    GEMINI_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY", "GOOGLE_API_KEY"),
    )
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Anthropic Claude 設定 (Step 42)
    ANTHROPIC_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
    )
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    # OpenRouter 設定 (統一LLMゲートウェイ)
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    # タスク別モデルルーティング (OpenRouter時に使用)
    OPENROUTER_ROUTING: dict[str, str] = {
        "planning": "google/gemini-2.0-flash",
        "plot_expansion": "google/gemini-2.0-flash",
        "writing": "anthropic/claude-3-5-sonnet-20241022",
        "climax": "anthropic/claude-3-5-sonnet-20241022",
        "audit": "google/gemini-2.0-flash",
        "marketing": "google/gemini-2.0-flash",
    }

    # Ollama 設定 (デフォルト: localhost:11434)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"

    # vLLM 設定 (デフォルト: localhost:8000)
    VLLM_BASE_URL: str = "http://localhost:8000"
    VLLM_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"

    # Embedding / GraphRAG (pgvector + Apache AGE) 設定
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_MODEL_FALLBACK: str = "text-embedding-3-small"
    AGE_GRAPH_NAME: str = "autonovel_graph"
    ENABLE_GRAPHRAG: bool = True

    # Vector / RAG (Phase: ハード依存化 Opt-in) 設定
    REQUIRE_PG: bool = False
    REQUIRE_CHROMA: bool = False
    RAG_FALLBACK_MODE: Literal["memory", "error"] = "memory"
    RAG_BATCH_SIZE: int = 64
    RERANKER_BACKEND: Literal["none", "simple", "cross_encoder"] = "none"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    CHROMA_DB_PATH: str = Field(default_factory=lambda: str(STORAGE_DIR / "chroma_db"))
    CHROMA_HOST: str = ""
    CHROMA_PORT: int = 8000
    AUTONOVEL_RAG_MODE: Literal["auto", "chroma", "memory"] = "auto"

    # マルチメディア展開 (Phase 7: Asset Pack / Media Mix / IF Routes / eBook)
    ENABLE_MULTIMEDIA: bool = False
    ENABLE_AUDIO_SYNTH: bool = False
    # 外部投稿プラグイン。`.env` に書かれた値を PluginRegistry が参照する。
    ENABLE_SOCIAL_POSTING: bool = False
    VOICEVOX_URL: str = "http://localhost:50021"
    VOICEVOX_DEFAULT_SPEAKER_ID: int = 3
    VOICEVOX_TIMEOUT_SECONDS: float = 30.0
    MULTIMEDIA_OUTPUT_DIR: str = Field(default_factory=lambda: str(STORAGE_DIR / "multimedia"))

    # ヘルスチェック詳細エンドポイント
    # 有効にすると LLM API を実際に呼び出すため費用が発生する（既定は無効）
    HEALTH_CHECK_LLM_PROBE: bool = False
    HEALTH_CHECK_TIMEOUT_SECONDS: float = 5.0

    # 画像生成プロバイダ設定 (DALL-E 3 / Stable Diffusion WebUI / ComfyUI / Mock)
    IMAGE_PROVIDER: Literal["mock", "dalle3", "sd_webui", "comfyui"] = "mock"
    DALL_E_API_KEY: str | None = None
    SD_WEBUI_URL: str | None = None
    COMFYUI_URL: str | None = None

    # Phase 4: Enrichment Agent
    ENRICHMENT_ENABLED: bool = False

    # 官能生成オプトイン (NSFW ガードレール)。
    # 明示的に True にしない限り官能生成経路は全拒否する（デフォルト拒否）。
    ENABLE_NSFW: bool = False

    # プロセ精練設定 (Step 9)
    PROSE_REFINER_ENABLED: bool = True
    PROSE_REFINER_MODEL: str = "gemini-2.0-flash"
    PROSE_REFINER_STYLE: str = "balanced"

    # Phase 2: Feature Flags
    BLIND_REVIEW_ENABLED: bool = True
    MULTI_LAYER_AUDIT_ENABLED: bool = True
    RAG_REFLECTION_ENABLED: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins をリスト形式で取得する。"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        """CORS の資格情報付きアクセスを許可してよいかを判定する。

        `CORS_ORIGINS` にワイルドカード `*` が含まれる場合、Any オリジンが
        資格情報（Cookie / Authorization）付きリクエストを信頼全世界に公開することになる。
        そのため `*` を含む場合は `False` を返し、呼び出し元に資格情報付き
        アクセスを強制的に無効化させる。
        """
        return ["*"] not in self.cors_origin_list

    @property
    def cors_allow_headers_list(self) -> list[str]:
        """許可する CORS ヘッダーをリスト形式で取得する。"""
        return [header.strip() for header in self.CORS_ALLOW_HEADERS.split(",") if header.strip()]

    def get_gemini_api_key(self) -> str:
        """GEMINI_API_KEY または GOOGLE_GENAI_API_KEY を安全・一元的に解決して返す (Step 38)."""
        import os
        return self.GEMINI_API_KEY or os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""

    def is_nsfw_enabled(self) -> bool:
        """官能生成が明示的にオプトインされているかを返す。

        `ENABLE_NSFW` が真の場合のみ官能生成経路を通す。既定は False で、
        官能生成はオプトアウト（デフォルト拒否）とする。
        """
        return bool(self.ENABLE_NSFW)


# グローバルな設定インスタンス
settings = Settings()


def is_auth_bypass_enabled(cfg: Settings) -> bool:
    """``AUTH_DISABLED`` による認証バイパスが許可されるかを判定する。

    本番環境 (``APP_ENV=production``) では、``AUTH_DISABLED`` の値にかかわらず
    必ず ``False`` を返す（纵深防御）。

    `Settings` の model_validator は本番 + ``AUTH_DISABLED=True`` を起動時に
    拒否するが、それは「設定が正しく構築された場合」にしか効かない。設定
    構築が将来リファクタされたり、環境変数が起動後に変わったりした場合に
    認証バイパスがそのまま残ると全エンドポイントが無認証で開くため、
    バイパスを**実際に捌くコード側**でもう 1 度環境を見る。

    引数 ``cfg`` を必須にしているのは、各モジュールが自身の束縛した
    ``settings`` を渡すため（テストが ``patch("...auth_middleware.settings")``
    のようにモジュール単位で差し替えるケースを壊さないため）。

    Args:
        cfg: 判定に使う設定オブジェクト。通常は当該モジュールの ``settings``。

    Returns:
        バイパスを許可する場合 ``True``。
    """
    if not bool(getattr(cfg, "AUTH_DISABLED", False)):
        return False
    return getattr(cfg, "APP_ENV", "") != "production"


def is_nsfw_enabled() -> bool:
    """官能生成が明示オプトインされているかを返す（モジュールレベルの省略形）。

    ``settings.is_nsfw_enabled()`` と同じ判定。`__all__` から見える名前として
    実在させるためのラッパー（存在しない名前を `__all__` に書くと
    `from ... import *` が実行時 AttributeError になるため）。
    """
    return settings.is_nsfw_enabled()


__all__ = ["Settings", "settings", "is_auth_bypass_enabled", "is_nsfw_enabled", "STORAGE_DIR", "ROOT_DIR"]



