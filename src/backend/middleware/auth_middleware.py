"""
src/backend/middleware/auth_middleware.py - グローバル認証ミドルウェア

公開パス（ヘルスチェック、メトリクス、認証エンドポイント、Webhook 等）を除き、
すべてのリクエストに対して JWT または API Key の検証を要求する。
未認証アクセスをデフォルトで拒絶（Default Deny）することで、
ルーター単位での認証設定漏れによる脆弱性を根本から排除する。
"""

from __future__ import annotations

import logging
import secrets
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.backend.config import settings
from src.backend.security.jwt import decode_token
from src.backend.security.stream_token import verify_stream_token

logger = logging.getLogger(__name__)

# 公開許可パス（完全一致、末尾スラッシュ除去後）
# 費用が発生する / 内部情報を含む detailed エンドポイントは公開しない
PUBLIC_EXACT_PATHS: set[str] = {
    "",
    "/health",
    "/health/live",
    "/health/liveness",
    "/health/ready",
    "/health/readiness",
    "/metrics",
    "/api/health",
    "/api/health/live",
    "/api/health/liveness",
    "/api/health/ready",
    "/api/health/readiness",
    "/api/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/billing/plans",
    "/api/billing/webhook",
    "/favicon.ico",
}

# 公開許可パスプレフィックス（静的アセット等）
# 検証方法: 完全一致、または「プレフィックス + 区切りスラッシュ」で始まる場合のみ。
# 単純な startswith だと `/api/streaming-xxx` のように境界で切れたパスまで
# まとめて公開されるため、必ず区切りを明示して判定する。
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/assets/",
    "/favicon",
    "/docs",
    "/redoc",
)

# ストリーム系エンドポイントのパス。ブラウザの EventSource / WebSocket は
# カスタムヘッダーを付けられないため、ここだけは短命・bookスコープの
# ストリームトークンをクエリパラメータで受け付ける。
# かつては "/api/stream" を PUBLIC_PREFIXES に丸ごと登録しており、
# 当該プレフィックス配下の全エンドポイントが default-deny の網から
# 完全に外れていた（最も守るべき最も広い範囲）。
STREAM_PATH_PREFIX = "/api/stream/"


def _matches_public_prefix(path: str) -> bool:
    """path が公開プレフィックスのいずれかに該当するか（スラッシュ境界を考慮）。"""
    for prefix in PUBLIC_PREFIXES:
        if path == prefix:
            return True
        if prefix.endswith("/"):
            if path.startswith(prefix):
                return True
        elif path.startswith(prefix + "/"):
            return True
    return False


def _extract_stream_book_id(path: str) -> int | None:
    """`/api/stream/writing/{book_id}/{ep_num}` 等から book_id を取り出す。"""
    if not path.startswith(STREAM_PATH_PREFIX):
        return None
    segments = [s for s in path[len(STREAM_PATH_PREFIX):].split("/") if s]
    # writing/{book_id}/{ep_num} / pipeline/{book_id}
    if not segments:
        return None
    candidate = segments[1] if segments[0] in ("writing", "pipeline") else segments[0]
    try:
        return int(candidate)
    except ValueError:
        return None


def is_public_path(path: str) -> bool:
    """公開パスとして無認証で通してもよいか."""
    normalized = path.rstrip("/")
    if normalized in PUBLIC_EXACT_PATHS:
        return True
    return _matches_public_prefix(path)


def is_safe_api_key_match(provided: str, expected: str) -> bool:
    """タイミング攻撃耐性を持つ定数時間でのAPIキー比較."""
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)



class GlobalAuthMiddleware(BaseHTTPMiddleware):
    """
    アプリケーション全体へのアクセスを保護する認証ミドルウェア。
    - Whitelist パス、AUTH_DISABLED=True、CORS preflight (OPTIONS) はバイパス
    - Bearer JWT または API Key (Authorization / X-API-Key) を検証
    - 検証失敗時は 401 Unauthorized を返却
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        path = request.url.path

        # 1. 開発/テスト用バイパス (AUTH_DISABLED=True またはテスト時の dependency_overrides)
        if settings.AUTH_DISABLED:
            return await call_next(request)

        app_obj = request.scope.get("app")
        overrides = getattr(app_obj, "dependency_overrides", None) if app_obj else None
        if overrides:
            from src.backend.auth import (
                get_current_user,
                require_admin_user_or_key,
                require_api_key,
            )

            if (
                get_current_user in overrides
                or require_api_key in overrides
                or require_admin_user_or_key in overrides
            ):
                return await call_next(request)

        # 2. CORS Preflight (OPTIONS) は通過
        if request.method == "OPTIONS":
            return await call_next(request)

        # 3. 公開ホワイトリスト判定 (完全一致 or スラッシュ境界を考慮したプレフィックス一致)
        if is_public_path(path):
            return await call_next(request)

        # 3b. ストリーム経路: 短命・bookスコープのストリームトークンのみ受理する。
        # EventSource/WebSocket はブラウザからヘッダーを付けられないため
        # クエリパラメータを許可するが、通常の access JWT は受け入れない
        # (クエリ経由で長期有効な認証情報がログに残るのを防ぐため)。
        if path.startswith(STREAM_PATH_PREFIX):
            stream_book_id = _extract_stream_book_id(path)
            stream_token = request.query_params.get("token", "")
            if stream_book_id is not None and verify_stream_token(stream_token, stream_book_id):
                return await call_next(request)

        # 4. 認証ヘッダーの取得と検証
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("X-API-Key", "")

        # 4a. API Key 検証 (X-API-Key または Authorization)
        allowed_keys_str = settings.ALLOWED_API_KEYS or ""
        allowed_keys = [k.strip() for k in allowed_keys_str.split(",") if k.strip()]

        if api_key_header and any(is_safe_api_key_match(api_key_header, k) for k in allowed_keys):
            return await call_next(request)

        # 4b. Authorization ヘッダー検証
        if auth_header:
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            else:
                token = auth_header.strip()

            # API Key として一致するか確認 (タイミングセーフ比較)
            if token and any(is_safe_api_key_match(token, k) for k in allowed_keys):
                return await call_next(request)

            # JWT トークンとして検証
            if token:
                try:
                    payload = decode_token(token, expected_type="access")
                    if payload and payload.get("sub"):
                        return await call_next(request)
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "無効または期限切れのトークンです"},
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                except Exception as exc:
                    logger.debug("AuthMiddleware: Token decode failed: %s", exc)
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "無効または期限切れのトークンです"},
                        headers={"WWW-Authenticate": "Bearer"},
                    )

        # 5. 未認証拒絶 (Default Deny)
        return JSONResponse(
            status_code=401,
            content={"detail": "認証が必要です"},
            headers={"WWW-Authenticate": "Bearer"},
        )


# Backward-compatible alias
AuthMiddleware = GlobalAuthMiddleware

