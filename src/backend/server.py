"""FastAPI アプリケーションのエントリポイント。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.backend.api.admin_phase2 import (
    enrichment_router as admin_enrichment_router,
    rag_router as admin_rag_router,
    router as admin_audit_router,
)
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.backend.config import settings
from src.backend.database import init_db
from src.backend.error_handlers import register_error_handlers
from src.backend.logging_config import configure as configure_logging
from src.backend.observability.health import build_health_payload, metrics
from src.backend.routers import (
    anti_ai,
    annotations,
    books,
    branches,
    chapters,
    collab,
    commercial,
    commercial_planning,
    cost,
    easy_mode,
    editor,
    episodes,
    export,
    graph,
    # `health` は下の `@app.get("/health") async def health()` に再束縛されるため、
    # モジュールとしては別名で持つ（mypy no-redef と、以降のコードが
    # `health.router` を参照して壊れる事故を防ぐ）。
    # 関数名は OpenAPI の operationId に使われるので rename しない。
    health as health_router,
    hooks,
    illustrations,
    issues,
    marketing,
    marketing_ctr,
    misc,
    multimedia,
    novel,
    patches,
    plots,
    projects,
    prompt_compare,
    prompt_versions,
    streaming,
    structure,
    styles,
    system,
    tasks,
    pipeline_stream,
    publishing,
    publishing_assistant,
    auth,
    billing,
    billing_webhook,
    trace,
    platform_export,
    stream_writing,
    subtext,
    orchestrated,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """アプリケーション起動時にログ設定と DB 初期化を行う lifespan ハンドラ。"""
    configure_logging()
    init_db()
    # 認証無効化は本番では起動拒否される（config.py のバリデータ）が、
    # 開発 / staging では黙って通る。設定し忘れを検知不能にしないため、
    # 起動時に必ず警告を出す（LLM キー欠落の warning と同じ階層）。
    if settings.AUTH_DISABLED:
        logger.warning(
            "[SECURITY WARNING] AUTH_DISABLED=true: authentication is BYPASSED "
            "and every request is treated as an admin user. "
            "This must never be enabled in a reachable environment. "
            "Remove it from .env immediately if this is unexpected."
        )
    # Step 46: Huey タスクキュー接続確認
    try:
        from src.backend.tasks.huey import check_huey_health
        health = check_huey_health()
        logger.info("Huey task queue initialized: %s", health)
    except Exception as e:
        logger.warning("Failed to check Huey health during startup: %s", e)

    # Step 44: LLMプロバイダの認証キー設定検証
    # Image generation provider keys are also checked here.
    if settings.LLM_PROVIDER == "gemini" and not settings.get_gemini_api_key():
        logger.warning("LLM_PROVIDER is 'gemini' but neither GEMINI_API_KEY nor GOOGLE_GENAI_API_KEY is configured.")
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
        try:
            from src.services.semantic_cache import cancel_all_prefetch

            cancelled = await cancel_all_prefetch()
            logger.info("shutdown: cancelled %d prefetch task(s)", cancelled)
        except Exception as e:
            logger.warning("Failed to cancel prefetch tasks during shutdown: %s", e)
        try:
            from src.core.executor_manager import executor_manager

            executor_manager.shutdown()
        except Exception as e:
            logger.warning("Failed to shutdown executor manager during shutdown: %s", e)
        logger.info("shutdown: background tasks cancelled")


app = FastAPI(title=f"{settings.APP_NAME} Backend", version=settings.APP_VERSION, lifespan=lifespan)



from src.backend.middleware.auth_middleware import GlobalAuthMiddleware
from src.security.headers import SecurityHeadersMiddleware

register_error_handlers(app)
app.add_middleware(GlobalAuthMiddleware)

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
# Step 19: マルチメディア無効時は不要なルーターをスキップする条件付きマウント
from src.core.plugin_registry import get_plugin_registry

plugin_registry = get_plugin_registry()

# コアルーター登録
app.include_router(easy_mode.router, prefix="/easy_mode", tags=["easy_mode"])
app.include_router(easy_mode.router, prefix="/api/wizard", tags=["wizard"])
if settings.APP_ENV == "development":
    app.include_router(easy_mode.router, prefix="/api/easy-mode", tags=["easy-mode"])
app.include_router(streaming.router, prefix="/easy_mode", tags=["streaming"])
app.include_router(styles.router)
app.include_router(graph.router)
app.include_router(editor.router)
app.include_router(system.router)
app.include_router(export.router)
app.include_router(platform_export.router)
app.include_router(stream_writing.router)

# 管理者・監査ルーター登録
app.include_router(admin_audit_router)
app.include_router(admin_rag_router)
app.include_router(admin_enrichment_router)

# 各ドメインルーターの静的登録
app.include_router(books.router)
app.include_router(plots.router)
app.include_router(episodes.router)
app.include_router(chapters.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(patches.router)
app.include_router(issues.router)
app.include_router(marketing.router)
app.include_router(marketing_ctr.router)
app.include_router(prompt_versions.router)
app.include_router(misc.router)
app.include_router(novel.router)
app.include_router(commercial.router)
app.include_router(commercial_planning.router)
app.include_router(collab.router)
app.include_router(illustrations.router)
# Step 19: multimedia プラグインが有効な場合のみマウント（DB初期化・タスク登録もスキップ）
if plugin_registry.is_enabled("multimedia"):
    app.include_router(multimedia.router, prefix="/multimedia", tags=["multimedia"])
else:
    logger.info("Multimedia plugin disabled; skipping /multimedia router mount")
app.include_router(branches.router)
app.include_router(anti_ai.router)
app.include_router(cost.router)
app.include_router(pipeline_stream.router)
app.include_router(publishing.router, prefix="/api/export")
app.include_router(publishing_assistant.router, prefix="/api")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(billing_webhook.router)
app.include_router(trace.router)
app.include_router(health_router.router)
app.include_router(subtext.router)
app.include_router(annotations.router)
app.include_router(hooks.router)
app.include_router(prompt_compare.router)
app.include_router(structure.router)
app.include_router(orchestrated.router)


@app.get("/health")
async def health() -> dict[str, object]:
    """ヘルスチェックエンドポイント (Phase 5: Step 55-57 拡充版)。

    DB 接続・Huey 生存確認・基本メトリクスを含めた総合ステータスを返す。
    全コンポーネント正常時は ``status=ok``、いずれか異常時は ``degraded``。
    互換性のため簡易 ``{"status": "ok"}`` のスーパーセットを返す。
    """
    logger.info("Health check invoked")
    return await build_health_payload()


@app.get("/metrics")
async def get_metrics() -> dict[str, int]:
    """メトリクスエンドポイント (Phase 5: Step 58)。

    プロセス内カウンタ (タスク投入数 / 完了数 / 失敗数 / エクスポート数 /
    ヘルスチェック呼出数) のスナップショットを返す。
    """
    return metrics.snapshot()
