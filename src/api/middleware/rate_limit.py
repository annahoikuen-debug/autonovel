"""認証系パス向けのレート制限ミドルウェア。

実体は :class:`src.backend.rate_limit.RateLimiter` に委譲する。
以前はこのモジュールが独自の固定ウィンドウ実装を持っており、

- プロセス内メモリのみ（ワーカー間で共有されない）
- ``request.client.host`` 固定（``TRUSTED_PROXY_CIDRS`` を無視）
- Redis 非対応

という問題があった。``RateLimiter`` は Redis 分散カウンタ、信頼プロキシを
考慮したクライアント IP 解決、メモリフォールバック時のキー数上限を備えている。
"""

from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.backend.rate_limit import RateLimiter

# パスプレフィックス → 1分あたりの許容リクエスト数
PathRateLimits = dict[str, int]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        path_rate_limits: PathRateLimits | None = None,
    ):
        """パス単位のレートリミッタ。

        ``path_rate_limits`` を渡すと、プレフィックスが一致したパスだけを
        制限し（例: 認証系だけ 10回/分）、無制限のグローバル上限は敷かない。
        ``None`` の場合は従来どおり全パスに ``requests_per_minute`` を適用する。
        """
        super().__init__(app)
        self.path_rate_limits = path_rate_limits
        self._limiters: dict[str | None, RateLimiter] = {}
        if path_rate_limits is None:
            self._limiters[None] = RateLimiter(
                max_requests=requests_per_minute,
                window_seconds=60,
                prefix="rate_limit:global",
            )
        else:
            for prefix, limit in path_rate_limits.items():
                self._limiters[prefix] = RateLimiter(
                    max_requests=limit,
                    window_seconds=60,
                    prefix=f"rate_limit:auth:{prefix.strip('/') or 'root'}",
                )

    def _resolve_limiter(self, path: str) -> RateLimiter | None:
        """このパスに適用する limiter を返す。対象外なら None。"""
        if self.path_rate_limits is None:
            return self._limiters.get(None)
        for prefix, limiter in self._limiters.items():
            if prefix is None:
                continue
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                return limiter
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        limiter = self._resolve_limiter(request.url.path)
        if limiter is None:
            return await call_next(request)

        try:
            await limiter.check(request)
        except HTTPException:
            # `dispatch` は ExceptionMiddleware の外側で動くため、
            # HTTPException を投げると 500 になる。429 を明示的に返す。
            return JSONResponse(
                {"detail": "Too Many Requests"},
                status_code=429,
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
