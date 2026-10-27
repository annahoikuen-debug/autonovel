import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from src.backend.config import settings

logger = logging.getLogger(__name__)


def get_secret_key() -> str:
    """現在の環境に応じた安全なJWT秘密鍵を取得する。"""
    return settings.get_jwt_secret_key()


def create_access_token(
    user_id: int | str | None = None,
    *,
    role: str = "user",
    expires_delta: timedelta | None = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """アクセストークンを発行する。

    Args:
        user_id: トークンの sub クレームに設定するユーザー ID。
        role: トークンの role クレーム。既定は "user"。
        expires_delta: 有効期限。未設定時は settings.ACCESS_TOKEN_EXPIRE_MINUTES を使用。
        extra_claims: トークンに追加したい任意クレーム（jti 等は自動付与）。
    """
    sub = str(user_id or "")
    to_encode: dict[str, Any] = {
        "sub": sub,
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, get_secret_key(), algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    user_id: int | str | None = None,
    *,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """リフレッシュトークンを発行する。"""
    sub = str(user_id or "")

    to_encode: dict[str, Any] = {
        "sub": sub,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, get_secret_key(), algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str | None = None) -> Optional[dict[str, Any]]:
    """JWT トークンをデコードしてペイロードを返す。

    期限切れ・署名不正・フォーマット不正などはそれぞれ個別にキャッチし、
    ログを出力したうえで None を返す。想定外の例外はスタックトレースを記録する。
    """
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        logger.warning("JWT token has expired: %s", exc)
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT token is invalid: %s", exc)
        return None
    except Exception as exc:  # 想定外のデコード障害
        logger.exception("JWT decode raised unexpected %s", type(exc).__name__)
        return None

    if expected_type and payload.get("type") != expected_type:
        logger.warning(
            "JWT token type mismatch: expected=%s, actual=%s",
            expected_type,
            payload.get("type"),
        )
        return None

    return payload