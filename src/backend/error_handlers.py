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
    """HTTPException を RFC 7807 形式に変換"""
    problem = ProblemDetails(
        type=f"https://autonovel.local/errors/http-{exc.status_code}",
        title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
        status=exc.status_code,
        detail=str(exc.detail),
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json"},
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
        loc = " -> ".join(str(l) for l in err.get("loc", []))
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
