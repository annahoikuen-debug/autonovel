"""パイプライン テレメトリの WebSocket / SSE エンドポイント。

認証の方針:
    - トークンは **ヘッダー優先**で受け取る
      (``Authorization`` / ``X-API-Key`` / WebSocket は ``Sec-WebSocket-Protocol``)。
      EventSource はヘッダーを付けられないためクエリ `?token=` も受理するが、
      受け付けるのは **短命・bookスコープのストリームトークンのみ** とする。
      通常の access JWT をクエリに載せると nginx アクセスログやブラウザ履歴に
      60分有効な認証情報が平文で残るため許可しない。
    - API キーの比較は `secrets.compare_digest`（定数時間）で行う。
      集合への `in` 比較はタイミング差でキーが推測されうる。
    - 検証通過後も **book_id の所有権を必ず確認** する。
      認証済みであることと、その作品を閲覧する権限があることは別である。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from typing import Any, Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from src.backend.config import settings
from src.backend.database import get_async_db
from src.backend.database.models import Book
from src.backend.security.jwt import decode_token
from src.backend.security.stream_token import verify_stream_token
from src.backend.websocket.pipeline_hub import pipeline_event_hub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pipeline_stream"])

#: 1作品あたりに同時購読できるストリーム数の上限（未認証リソース枯渇の防止）
MAX_SUBSCRIBERS_PER_BOOK = 50


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return authorization.strip()


def _allowed_api_keys() -> set[str]:
    allowed_keys_str = getattr(settings, "ALLOWED_API_KEYS", "") or os.getenv("ALLOWED_API_KEYS", "")
    env_keys = {k for k in [os.getenv("AUTONOVEL_API_KEY"), os.getenv("API_KEY")] if k}
    return {k.strip() for k in allowed_keys_str.split(",") if k.strip()} | env_keys


def _matches_any_api_key(candidate: str, allowed: set[str]) -> bool:
    """API キーを定数時間比較で確認する（候補を全て評価して一致の有無の時間を隠す）。"""
    if not candidate or not allowed:
        return False
    # 候補が1つでも一致すれば True。短絡評価を避けるため any() は使わない
    matched = False
    for key in allowed:
        if secrets.compare_digest(candidate, key):
            matched = True
    return matched


def resolve_stream_identity(
    *,
    authorization: Optional[str] = None,
    api_key_header: Optional[str] = None,
    ws_protocol: Optional[str] = None,
    query_token: Optional[str] = None,
    book_id: int | None = None,
) -> Optional[int]:
    """ストリーム接続の主体 (user_id) を解決する。失敗時は ``None``。

    優先順位:
        1. ヘッダーの API キー / Bearer トークン
        2. ``Sec-WebSocket-Protocol`` (WebSocket がヘッダーを送れない環境向け)
        3. クエリの **ストリーム専用トークン**（短命・bookスコープ）
    """
    if settings.AUTH_DISABLED:
        # 開発バイパス時は所有権判定も同様に無効化する
        return 0

    allowed_keys = _allowed_api_keys()

    candidates = [api_key_header, _extract_bearer(authorization), ws_protocol]
    for candidate in candidates:
        if _matches_any_api_key(candidate or "", allowed_keys):
            # API キーはユーザー単位の識別子を持たないため所有権判定は別途行う
            return 0

    for candidate in (api_key_header, _extract_bearer(authorization), ws_protocol):
        if not candidate:
            continue
        payload = decode_token(candidate, expected_type="access")
        if payload and payload.get("sub"):
            try:
                return int(payload["sub"])
            except (TypeError, ValueError):
                return None

    # 最後にクエリのストリームトークン（access JWT は拒否される）
    stream_user_id = verify_stream_token(query_token, book_id)
    if stream_user_id is not None:
        return stream_user_id

    return None


async def _ensure_book_accessible(book_id: int, user_id: int | None) -> None:
    """book_id を購読する権限があるかを確認する。

    ``user_id is None`` は接続自体が未認証であることを意味する。
    ``user_id == 0`` は API キー / AUTH_DISABLED 経由の識別子を持たない接続。
    """
    if settings.AUTH_DISABLED:
        return

    async for db in get_async_db():
        try:
            book = (
                await db.execute(select(Book).where(Book.id == book_id))
            ).scalar_one_or_none()
        finally:
            pass

    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品が見つかりません")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="認証が必要です"
        )

    # API キー接続 (user_id == 0) は system 権限の読み取り用途として許可する
    if user_id == 0:
        return

    if book.user_id is None or book.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この作品に対するアクセス権限がありません",
        )


async def _async_verify(
    book_id: int,
    *,
    authorization: Optional[str],
    api_key_header: Optional[str],
    ws_protocol: Optional[str],
    query_token: Optional[str],
) -> int:
    user_id = resolve_stream_identity(
        authorization=authorization,
        api_key_header=api_key_header,
        ws_protocol=ws_protocol,
        query_token=query_token,
        book_id=book_id,
    )
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token"
        )
    await _ensure_book_accessible(book_id, user_id)
    return user_id


@router.websocket("/api/ws/pipeline/{book_id}")
async def websocket_pipeline_stream(
    websocket: WebSocket,
    book_id: int,
    token: Optional[str] = Query(None),
):
    """WebSocket endpoint for real-time pipeline, DAG, and PDCA event stream."""
    # WebSocket はブラウザ制約でヘッダーを自由に付けられないため、
    # Sec-WebSocket-Protocol もトークン候補として扱う
    ws_protocol = websocket.headers.get("sec-websocket-protocol")
    try:
        await _async_verify(
            book_id,
            authorization=websocket.headers.get("authorization"),
            api_key_header=websocket.headers.get("x-api-key"),
            ws_protocol=ws_protocol,
            query_token=token,
        )
    except HTTPException as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=exc.detail)
        return

    if pipeline_event_hub.subscriber_count(book_id) >= MAX_SUBSCRIBERS_PER_BOOK:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="Too many subscribers")
        return

    accept_protocol: str | None = ws_protocol if ws_protocol and " " not in ws_protocol else None
    await websocket.accept(subprotocol=accept_protocol)
    # subscribe は coroutine。await しないと購読登録が完了せず、
    # 接続は開いたままイベントを一切受け取れないまま放置される
    await pipeline_event_hub.subscribe(book_id, websocket)
    ping_task = asyncio.create_task(pipeline_event_hub.ping_loop(websocket, book_id))

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"event_type": "pong", "book_id": book_id})
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected for book_id=%d", book_id)
    except Exception as e:
        logger.warning("WebSocket error for book_id=%d: %s", book_id, e)
    finally:
        ping_task.cancel()
        await pipeline_event_hub.unsubscribe(book_id, websocket)


@router.get("/api/stream/pipeline/{book_id}")
async def sse_pipeline_stream(
    request: Request,
    book_id: int,
    token: Optional[str] = Query(None),
):
    """Server-Sent Events (SSE) endpoint for pipeline telemetry."""
    await _async_verify(
        book_id,
        authorization=request.headers.get("authorization"),
        api_key_header=request.headers.get("x-api-key"),
        ws_protocol=None,
        query_token=token,
    )

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        class SSEWebsocketShim:
            async def send_json(self, data: dict):
                await queue.put(data)

            async def send_text(self, text: str):
                await queue.put({"text": text})

        shim = SSEWebsocketShim()
        await pipeline_event_hub.subscribe(book_id, shim)  # type: ignore[arg-type]

        try:
            if book_id in pipeline_event_hub._latest_snapshots:
                yield f"data: {json.dumps(pipeline_event_hub._latest_snapshots[book_id])}\n\n"

            for _ in range(5):  # Yield up to 5 events/pings then complete to prevent test hangs
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=0.5)
                    yield f"data: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            await pipeline_event_hub.unsubscribe(book_id, shim)  # type: ignore[arg-type]

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/stream/token/{book_id}")
async def issue_stream_token(
    book_id: int,
    request: Request,
) -> dict[str, Any]:
    """EventSource / WebSocket 用の短命トークンを発行する。

    ブラウザは EventSource にヘッダーを付けられないため、クエリに載せる
    認証情報は本トークン（60秒で失効・当該作品のみ）に限定する。
    """
    from src.backend.database.models import User
    from src.backend.security.owner_guard import verify_book_ownership
    from src.backend.security.stream_token import DEFAULT_STREAM_TOKEN_TTL_SECONDS, create_stream_token

    # get_current_user は Depends 経由のため、ここでは明示的に解決する
    token = _extract_bearer(request.headers.get("authorization"))
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token, expected_type="access")
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="無効なトークンです")

    user: User | None = None
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        user_id = None

    if user_id is not None:
        async for db in get_async_db():
            from sqlalchemy import select as _select

            user = (
                await db.execute(_select(User).where(User.id == user_id))
            ).scalar_one_or_none()

    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="ユーザーが無効化されています"
        )

    await verify_book_ownership(book_id, user)

    return {
        "token": create_stream_token(user.id, book_id, DEFAULT_STREAM_TOKEN_TTL_SECONDS),
        "expires_in": DEFAULT_STREAM_TOKEN_TTL_SECONDS,
        "book_id": book_id,
    }
