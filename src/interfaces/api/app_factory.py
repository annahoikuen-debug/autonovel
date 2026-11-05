"""FastAPI アプリケーションファクトリ（TRACK-A9 / F3 DI リファクタ）。

TRACK-A9: `src/backend/server.py` の起動ロジック（lifespan, ミドルウェア,
ルーター登録, エンドポイント）を本モジュールに集約した。

F3: ルーター群・init_db・エラーハンドラ・認証ミドルウェア・ヘルス/
メトリクス・Huey 確認・プリフェッチ取り消しはすべて ``AppWiring`` として
コンポジションルート（``src/backend/wiring.py``）から注入される。
本モジュールは ``src.backend`` / ``src.services`` を import しない
（レイヤー契約2: 正規レイヤー → 旧モノリス禁止）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.middleware.rate_limit import RateLimitMiddleware
from src.core.plugin_registry import get_plugin_registry
from src.infrastructure.config.settings import settings
from src.infrastructure.logging_config import configure as configure_logging
from src.security.headers import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouterMount:
    """1 件のルーター登録指示（prefix / tags / プラグイン条件付き）。"""

    router: APIRouter
    prefix: str = ""
    tags: tuple[str, ...] | None = None
    plugin: str | None = None


@dataclass(frozen=True)
class AppWiring:
    """アプリ組み立てに必要な依存一式。

    すべてコンポジションルートから注入され、本モジュールは旧モノリスを
    直接 import しない。
    """

    routers: tuple[RouterMount, ...]
    init_db: Callable[..., None]
    register_error_handlers: Callable[[FastAPI], None]
    auth_middleware: type[BaseHTTPMiddleware]
    build_health_payload: Callable[[], Awaitable[dict[str, Any]]]
    health_metrics: Any
    huey_check: Callable[[], Any] | None = None
    cancel_prefetch: Callable[[], Awaitable[int]] | None = None


def build_lifespan(wiring: AppWiring) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """``wiring`` に供給された依存で lifespan ハンドラを組み立てる。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """アプリケーション起動時にログ設定と DB 初期化を行う lifespan ハンドラ。"""
        configure_logging()
        wiring.init_db()
        # AUTH_DISABLED による認証バイパスの起動時警告（縦深防御：発生検知）
        # 本番環境では Settings バリデータで AUTH_DISABLED=True を拒否するが、
        # 設定構築後の環境変数変更や開発環境での戻し忘れに備え、
        # アプリ側でもう一度環境を参照して警告を出す。
        if settings.AUTH_DISABLED and settings.APP_ENV != "production":
            logger.warning(
                "[AUTH WARNING] AUTH_DISABLED=true が有効です（APP_ENV=%s）。"
                "認証がバイパスされ、全エンドポイントが無認証で開かれます。"
                "開発完了後は必ず AUTH_DISABLED=false に戻してください。",
                settings.APP_ENV,
            )
        # Step 46: Huey タスクキュー接続確認
        if wiring.huey_check is not None:
            try:
                health = wiring.huey_check()
                logger.info("Huey task queue initialized: %s", health)
            except Exception as e:
                logger.warning("Failed to check Huey health during startup: %s", e)

        # Step 44: LLMプロバイダの認証キー設定検証
        # Image generation provider keys are also checked here.
        if settings.LLM_PROVIDER == "gemini" and not settings.get_gemini_api_key():
            logger.warning(
                "LLM_PROVIDER is 'gemini' but neither GEMINI_API_KEY nor GOOGLE_GENAI_API_KEY is configured."
            )
        elif settings.LLM_PROVIDER == "openai" and not settings.OPENAI_API_KEY:
            logger.warning("LLM_PROVIDER is 'openai' but OPENAI_API_KEY is not configured.")
        elif settings.LLM_PROVIDER == "claude" and not settings.ANTHROPIC_API_KEY:
            logger.warning("LLM_PROVIDER is 'claude' but ANTHROPIC_API_KEY is not configured.")
        elif settings.LLM_PROVIDER == "openrouter" and not settings.OPENROUTER_API_KEY:
            logger.warning("LLM_PROVIDER is 'openrouter' but OPENROUTER_API_KEY is not configured.")
        elif settings.LLM_PROVIDER == "ollama":
            logger.info("LLM_PROVIDER is 'ollama' (local server). No API key required.")
        elif settings.LLM_PROVIDER == "vllm":
            logger.info("LLM_PROVIDER is 'vllm' (local server). No API key required.")

        if settings.IMAGE_PROVIDER == "dalle3" and not settings.DALL_E_API_KEY:
            logger.warning("IMAGE_PROVIDER is 'dalle3' but DALL_E_API_KEY is not configured.")
        elif settings.IMAGE_PROVIDER == "sd_webui" and not settings.SD_WEBUI_URL:
            logger.warning("IMAGE_PROVIDER is 'sd_webui' but SD_WEBUI_URL is not configured.")
        elif settings.IMAGE_PROVIDER == "comfyui" and not settings.COMFYUI_URL:
            logger.warning("IMAGE_PROVIDER is 'comfyui' but COMFYUI_URL is not configured.")

        # PLAN_W6 Step 7: shutdown 枝。プロセス終了時にバックグラウンドタスクが
        # 中断されると RAG 検索中の DB 接続がリークするため、明示的に取り消す。
        try:
            yield
        finally:
            if wiring.cancel_prefetch is not None:
                try:
                    cancelled = await wiring.cancel_prefetch()
                    logger.info("shutdown: cancelled %d prefetch task(s)", cancelled)
                except Exception as e:
                    logger.warning("Failed to cancel prefetch tasks during shutdown: %s", e)
            try:
                from src.core.executor_manager import executor_manager

                executor_manager.shutdown()
            except Exception as e:
                logger.warning("Failed to shutdown executor manager during shutdown: %s", e)
            logger.info("shutdown: background tasks cancelled")

    return lifespan


def create_app(
    wiring: AppWiring,
    *,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """``wiring`` の依存で FastAPI アプリケーションインスタンスを生成して返す。"""
    if lifespan is None:
        lifespan = build_lifespan(wiring)

    app = FastAPI(
        title=f"{settings.APP_NAME} Backend",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    wiring.register_error_handlers(app)
    app.add_middleware(wiring.auth_middleware)

    # 認証系エンドポイントのみ IP 単位のレート制限を適用する。
    # `/api/auth/login` と `/api/auth/register` は認証なしで到達でき、
    # 制限しないとパスワード総当たりと、アカウント大量作成（登録ごとに
    # credits=50 を付与される LLM 予算の悪用）が可能になる。
    # グローバルな上限は設定せず、認証パスにだけ上限を置くことで
    # ストリーミングやバッチ生成など他ルートの実運用を阻害しない。
    AUTH_PATH_RATE_LIMITS: dict[str, int] = {
        "/api/auth/login": 10,
        "/api/auth/register": 5,
        "/api/auth/refresh": 30,
    }
    app.add_middleware(RateLimitMiddleware, path_rate_limits=AUTH_PATH_RATE_LIMITS)

    # レスポンスにセキュリティヘッダー (HSTS / X-Frame-Options / CSP 等) を付与する。
    app.add_middleware(SecurityHeadersMiddleware)

    # `CORS_ORIGINS` に `*` が含まれている場合、資格情報 (Cookie / Authorization) を
    # 伴うアクセスを信頼するのは危険（リフレクションで全オリジンに許可される）。
    # 本番起動は禁止し、それ以外は資格情報付きを強制無効化+loud warning する。
    _cors_allow_credentials = settings.cors_allow_credentials
    if not _cors_allow_credentials:
        logger.warning(
            "[SECURITY WARNING] CORS_ORIGINS contains '*'; forcing allow_credentials=False. "
            "Set an explicit origin list if credentialed cross-origin access is required."
        )
    if settings.APP_ENV == "production" and not _cors_allow_credentials:
        raise RuntimeError(
            "本番環境 (APP_ENV=production) では CORS_ORIGINS に '*' を設定できません。"
            "公開オリジンを明示的に列挙してください。"
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=_cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=settings.cors_allow_headers_list,
    )

    # コアルーター登録
    # Step 19: プラグイン無効時は該当ルーターをスキップする条件付きマウント
    plugin_registry = get_plugin_registry()
    for mount in wiring.routers:
        if mount.plugin is not None and not plugin_registry.is_enabled(mount.plugin):
            logger.info(
                "%s plugin disabled; skipping %s router mount",
                mount.plugin,
                mount.prefix or "unnamed",
            )
            continue
        include_kwargs: dict[str, Any] = {}
        if mount.prefix:
            include_kwargs["prefix"] = mount.prefix
        if mount.tags:
            include_kwargs["tags"] = list(mount.tags)
        app.include_router(mount.router, **include_kwargs)

    @app.get("/health")
    async def health() -> dict[str, object]:
        """ヘルスチェックエンドポイント (Phase 5: Step 55-57 拡充版)。

        DB 接続・Huey 生存確認・基本メトリクスを含めた総合ステータスを返す。
        全コンポーネント正常時は ``status=ok``、いずれか異常時は ``degraded``。
        互換性のため簡易 ``{"status": "ok"}`` のスーパーセットを返す。
        """
        logger.info("Health check invoked")
        return await wiring.build_health_payload()

    @app.get("/metrics")
    async def get_metrics() -> dict[str, int]:
        """メトリクスエンドポイント (Phase 5: Step 58)。

        プロセス内カウンタ (タスク投入数 / 完了数 / 失敗数 / エクスポート数 /
        ヘルスチェック呼出数) のスナップショットを返す。
        """
        return wiring.health_metrics.snapshot()

    return app
