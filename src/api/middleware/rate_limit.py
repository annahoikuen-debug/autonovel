import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# パスプレフィックス → 1分あたりの許容リクエスト数
PathRateLimits = dict[str, int]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        path_rate_limits: PathRateLimits | None = None,
    ):
        """IP 単位の固定ウィンドウレートリミッタ。

        ``path_rate_limits`` を渡すと、プレフィックスが一致したパスだけを
        制限し（例: 認証系だけ 10回/分）、無制限のグローバル上限は敷かない。
        ``None`` の場合は従来どおり全パスに ``requests_per_minute`` を適用する。
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.path_rate_limits = path_rate_limits
        self.window_size = 60  # seconds
        self.clients = {}  # In production, use Redis or similar

    def _resolve_limit(self, path: str) -> int | None:
        """このパスに適用する上限を返す。上限なし（非制限）なら None。"""
        if self.path_rate_limits is None:
            return self.requests_per_minute
        for prefix, limit in self.path_rate_limits.items():
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                return limit
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        limit = self._resolve_limit(request.url.path)
        if limit is None:
            return await call_next(request)

        client_ip = request.client.host
        current_time = time.time()

        # Clean old entries (simple cleanup, not production ready)
        self.clients = {
            ip: data for ip, data in self.clients.items()
            if current_time - data["first_request_time"] < self.window_size
        }

        if client_ip not in self.clients:
            # First request from this IP
            self.clients[client_ip] = {
                "first_request_time": current_time,
                "request_count": 1,
            }
        else:
            data = self.clients[client_ip]
            if current_time - data["first_request_time"] > self.window_size:
                # Reset the window
                data["first_request_time"] = current_time
                data["request_count"] = 1
            else:
                data["request_count"] += 1
                if data["request_count"] > limit:
                    # `dispatch` は ExceptionMiddleware の外側で動くため、
                    # ここで HTTPException を投げると 500 として返ってしまう。
                    # 429 を明示的なレスポンスとして返す。
                    return Response(
                        content='{"detail":"Too Many Requests"}',
                        status_code=429,
                        media_type="application/json",
                        headers={"Retry-After": str(self.window_size)},
                    )

        response = await call_next(request)
        return response
