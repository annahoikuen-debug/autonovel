"""グローバル例外ハンドラ (RFC 7807 準拠)。"""
import logging

from fastapi import Request, HTTPException, status, FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from src.backend.exceptions import AutoNovelException
from src.backend.schemas.problem_details import ProblemDetails
from src.core.exceptions.base import HegemonyError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # ドメイン例外は status_code を持つが、ハンドラ未登録のまま 500 に落ちていたため登録する
    app.add_exception_handler(AutoNovelException, domain_exception_handler)
    app.add_exception_handler(HegemonyError, domain_exception_handler)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException を RFC 7807 形式に変換する。

    status 500 の detail は内部情報 (例外本文・DB エラー等) になり得るため
    汎用文に置換してマスクし、原文はサーバログにのみ残す。
    (旧実装は `HTTPException(500, str(exc))` の detail をそのまま返し、
    ドメイン例外向けの 5xx マスク機構をバイパスして内部情報を漏洩していた。)

    501-504 は「Multimedia disabled」「beat 生成に失敗」等の
    **意図的なプロトコルメッセージ**であり、クライアントが分類に使うため
    そのまま返す (マスクすると API 契約を壊す)。
    """
    status_code = exc.status_code
    if status_code == 500:
        logger.error(
            "HTTPException %s on %s: detail=%r",
            status_code,
            request.url.path,
            exc.detail,
            exc_info=exc.__cause__ or None,
        )
        title = "サーバー内部でエラーが発生しました"
        detail = "Internal Server Error"
    else:
        title = exc.detail if isinstance(exc.detail, str) else "HTTP Error"
        detail = str(exc.detail)

    problem = ProblemDetails(
        type=f"https://autonovel.local/errors/http-{status_code}",
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
    )
    # WWW-Authenticate (401) や Retry-After (429) 等のヘッダを転送する
    response_headers = {"Content-Type": "application/problem+json"}
    if exc.headers:
        response_headers.update(exc.headers)
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        headers=response_headers,
    )


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """`AutoNovelException` / `HegemonyError` を RFC 7807 形式に変換する。

    両者とも `status_code` (404 / 409 / 422 / 429 / 503 など) を持つため、
    それをそのまま応答ステータスに使用する。
    5xx 系は内部情報なので詳細は伏せ、サーバログにのみ記録する。
    """
    status_code = getattr(exc, "status_code", None) or status.HTTP_500_INTERNAL_SERVER_ERROR
    if not isinstance(status_code, int) or not (400 <= status_code <= 599):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    if status_code >= 500:
        logger.exception("Unhandled domain exception: %s", exc)
        title = "サーバー内部でエラーが発生しました"
        detail = f"{type(exc).__name__}: {exc}" if status_code < 500 else "Internal Server Error"
    else:
        title = str(exc) or type(exc).__name__
        detail = str(exc)

    problem = ProblemDetails(
        type=f"https://autonovel.local/errors/domain-{status_code}",
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json"},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic バリデーションエラーを RFC 7807 形式に変換"""
    invalid_params = []
    for err in exc.errors():
        loc = " -> ".join(str(part) for part in err.get("loc", []))
        invalid_params.append({
            "name": loc,
            "reason": err.get("msg", "Invalid value"),
        })

    problem = ProblemDetails(
        type="https://autonovel.local/errors/validation-error",
        title="リクエストパラメータの検証に失敗しました",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="送信されたデータに形式または値の不正があります",
        instance=request.url.path,
        invalid_params=invalid_params,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=problem.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json"},
    )
