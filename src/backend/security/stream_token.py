"""ストリーム接続専用トークン (EventSource / WebSocket 用)。

ブラウザの `EventSource` と `WebSocket` はカスタム Authorization ヘッダーを
付けられない。そのため従来はクエリ文字列に**通常の access JWT** を
載せるしかなく、以下のような問題を生んでいた:

- nginx アクセスログ・ブラウザ履歴・中間プロキシのログに
  長期有効な JWT が平文で残り続ける
- 漏れたトークンで 60 分間も、全API がアクセス可能

そこで、通常の access/refresh トークンとは別に、**数十秒で失効し、
1作品のみにスコープされた**ストリーム専用トークンを発行する。
クエリ文字列に載せてよいのはこの短命トークンのみとする。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from src.backend.config import settings
from src.backend.security.jwt import get_secret_key

logger = logging.getLogger(__name__)

#: ストリームトークンの type クレーム。access/refresh と必ず区別する。
STREAM_TOKEN_TYPE = "stream"

#: デフォルト有効期間。接続確立にのみ必要なので短く保つ。
DEFAULT_STREAM_TOKEN_TTL_SECONDS = 60


def create_stream_token(
    user_id: int | str,
    book_id: int,
    ttl_seconds: int = DEFAULT_STREAM_TOKEN_TTL_SECONDS,
) -> str:
    """指定作品のみを購読できる短命トークンを発行する。"""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "book_id": int(book_id),
        "type": STREAM_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=max(1, int(ttl_seconds))),
    }
    return jwt.encode(payload, get_secret_key(), algorithm=settings.JWT_ALGORITHM)


def verify_stream_token(token: Optional[str], book_id: int | None = None) -> Optional[int]:
    """ストリームトークンを検証し、発行元の user_id を返す。

    ``book_id`` を渡すと、その作品にスコープされたトークンのみを許可する。
    検証に失敗した場合は例外を出さず ``None`` を返す（呼び出し側で 401 を返す）。
    """
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        logger.debug("Stream token decode failed: %s", exc)
        return None
    except Exception as exc:  # 想定外のデコード障害でも接続全体は落とさない
        logger.warning("Stream token decode raised unexpectedly: %s", exc)
        return None

    # access トークンをストリーム用途で使い回すことを防ぐ
    if payload.get("type") != STREAM_TOKEN_TYPE:
        return None

    sub = payload.get("sub")
    if sub is None or not str(sub).strip():
        return None

    if book_id is not None:
        try:
            token_book_id = int(payload.get("book_id"))
        except (TypeError, ValueError):
            return None
        if token_book_id != int(book_id):
            return None

    try:
        return int(sub)
    except (TypeError, ValueError):
        return None


__all__ = [
    "STREAM_TOKEN_TYPE",
    "DEFAULT_STREAM_TOKEN_TTL_SECONDS",
    "create_stream_token",
    "verify_stream_token",
]
