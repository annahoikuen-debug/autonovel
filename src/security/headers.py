from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Swagger UI / ReDoc は CDN の JS・CSS と inline style に依存しているため、
# アプリ用の CSP をそのまま当てるとページが真っ白になる。ここでは両者だけ
# CSP を付けない（自我完結した静的ファイルを配信するルートのため）。
DOCS_PATHS: frozenset[str] = frozenset({"/docs", "/redoc"})

# アプリ応答に付与する CSP。
# - `upgrade-insecure-requests` は含めない（HTTP 開発環境や reverse proxy 経由で
#   mixed content が誤ってUpgradeされ、SSE 接続が落ちるのを避ける）
# - `connect-src` は 'self' と API オリジンのみ。EventSource (SSE) も
#   connect-src の対象なので、ここを絞ってはいけない
# - `frame-ancestors 'none'` が X-Frame-Options: DENY を CSP 側でも担保する
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' data: blob:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        # Security headers
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Content Security Policy
        # 静的ドキュメント (Swagger UI / ReDoc) は CDN 依存のため CSP を外す
        if request.url.path not in DOCS_PATHS:
            response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        return response
