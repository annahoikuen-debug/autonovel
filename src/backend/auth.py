"""
src/backend/auth.py — API 認証・認可ユーティリティ

認証手段と書き込み権限の対応（運用方針）:

=============  ==========================================================
手段           許可される操作
=============  ==========================================================
JWT (Bearer)   読み書きすべて（``get_current_user`` / ``require_admin_user``）
API キー        **読み取り専用**（GET/HEAD/OPTIONS）
=============  ==========================================================

書き込み系 (POST/PUT/PATCH/DELETE) に ``require_api_key`` を付けるのは不可。
同一の Authorization ヘッダーで JWT と API キーの両方を要求すると、
本番では到達不能なエンドポイントになる（片方しか送れない）。
サーバー間連携で API キーによる書き込みが必要な場合のみ
``get_current_user_or_service_key`` + ``ALLOW_API_KEY_WRITES=True`` を使う。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.config import settings
from src.backend.database import get_async_db
from src.backend.database.models import User
from src.backend.security.jwt import decode_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _get_dev_mock_user() -> User:
    """開発・テスト用のモック管理者ユーザーを生成する。"""
    user = User(
        id=1,
        email="dev@autonovel.local",
        display_name="Dev Admin",
        role="admin",
        status="active",
        plan_tier="enterprise",
        credits=99999,
    )
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """現在の認証済みユーザーを取得する。
    AUTH_DISABLED が True の場合は、開発用モックユーザーを返却してバイパスする。
    """
    if settings.AUTH_DISABLED:
        return _get_dev_mock_user()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なトークンです",
        )
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なトークンペイロードです",
        )

    user_id = int(sub) if isinstance(sub, (int, str)) and str(sub).isdigit() else sub
    user = await db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザーが存在しないか、無効化されています",
        )
    return user


async def require_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """管理者ロール（admin）を必須とする認可依存性。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者権限が必要です",
        )
    return current_user


async def get_current_user_or_service_key(
    token: str = Depends(oauth2_scheme),
    authorization: str = Header(default="", alias="Authorization"),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """サーバー間連携向けの書き込み認証依存性（commercial 系）。

    書き込みは既定で **JWT のみ** を受け付ける（API キーは読み取り専用、
    :func:`require_admin_user_or_key` と同じ方針）。

    旧実装は ``require_api_key`` を個別エンドポイントに並べていたが、
    これは JWT と API キーを **同じ Authorization ヘッダー** で要求しているため、
    本番 (``AUTH_DISABLED=False``) ではどちらか一方しか送れない以上、
    両方を通過するリクエストは原理的に存在せず到達不能になっていた。
    さらに API キー経由の書き込みは ``_get_dev_mock_user()`` に user id=1 を
    与えてしまっていたため、共有 API キー 1 本で全ユーザーを装える権限昇格でもある。
    この依存は JWT 優先 + 設定オプトインの API キー受付に置き換え、
    API キー経由時のみサービスアカウントを解決する。

    設定:
        ``ALLOW_API_KEY_WRITES`` が True の環境のみ、有効な API キーを
        サーバー間連携の資格情報として受け付ける。その場合の書き込み主体は
        ``API_KEY_SERVICE_EMAIL`` で指定されたサービスアカウントであり、
        任意ユーザーへのなりすましは行わない。アカウントが未登録なら
        「誰の権限で書き込んでいるか不明」のまま実行させないため 403 で拒否する。
    """
    if settings.AUTH_DISABLED:
        return _get_dev_mock_user()

    if token:
        return await get_current_user(token=token, db=db)

    if not getattr(settings, "ALLOW_API_KEY_WRITES", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="この操作には JWT (Bearer トークン) が必要です (API キーは読み取り専用です)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key = await require_api_key(authorization)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from sqlalchemy import select

    service_email = getattr(settings, "API_KEY_SERVICE_EMAIL", "") or ""
    user = None
    if service_email:
        user = (await db.execute(select(User).where(User.email == service_email))).scalar_one_or_none()
    if user is None or user.status != "active":
        logger.error(
            "ALLOW_API_KEY_WRITES=True ですがサービスアカウント %r が見つからないか無効です。書き込みは拒否しました。",
            service_email,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("API キーによる書き込みは許可されていません（サービスアカウントが未登録です）"),
        )
    return user


async def require_api_key(
    authorization: str = Header(default="", alias="Authorization"),
) -> str:
    """APIキーの検証を行う依存性関数。
    AUTH_DISABLED が True の場合のみ開発キーを許可し、それ以外は厳格に検証する。
    """
    if settings.AUTH_DISABLED:
        return "dev-key"

    # Extract token from header
    token = ""
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif authorization:
        token = authorization.strip()

    # Validate the extracted token
    result = validate_api_key_sync(token)
    if result is False:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return result  # token string


async def require_admin_user_or_key(
    token: str = Depends(oauth2_scheme),
    authorization: str = Header(default="", alias="Authorization"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None,
) -> User:
    """管理者JWTまたは有効なAPI Keyのいずれかを要求する依存性関数。

    API キー経由のアクセスは **読み取り専用** とする (``api_readonly`` ロール)。
    旧実装は api_readonly を返すだけで、それを検査する依存が無かったため、
    共有 API キー 1 本で全管理者 POST (サーキットブレイカーリセット、
    スキル切替、A/B テスト実行など) を実行できる権限昇格が発生していた。
    書き込み系メソッド (POST/PUT/PATCH/DELETE) は admin JWT を要求する。
    """
    if settings.AUTH_DISABLED:
        return _get_dev_mock_user()

    if token:
        user = await get_current_user(token=token, db=db)
        if user.role == "admin":
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者権限が必要です",
        )

    # API Key を試行
    key = await require_api_key(authorization)
    if key:
        # API Key 保持者には読み取り専用ロールを付与（admin 昇格しない）
        method = request.method if request is not None else "GET"
        if method in ("GET", "HEAD", "OPTIONS"):
            api_user = _get_dev_mock_user()
            api_user.role = "api_readonly"
            return api_user
        # 書き込み系は API キーでは実行不可 (権限昇格の防止)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この操作には管理者 JWT が必要です (API キーは読み取り専用です)",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="管理者認証または有効なAPI Keyが必要です",
    )


def validate_api_key_sync(api_key: str) -> str | bool:
    """同期コンテキスト用のAPIキー検証ヘルパー（タイミング攻撃耐性版）"""
    if settings.AUTH_DISABLED:
        return "dev-key"
    if not api_key:
        return False
    allowed_keys_str = getattr(settings, "ALLOWED_API_KEYS", "") or os.environ.get("ALLOWED_API_KEYS", "")
    allowed_keys = [k.strip() for k in allowed_keys_str.split(",") if k.strip()]
    if not allowed_keys:
        return False
    import hmac

    is_valid = any(hmac.compare_digest(api_key, k) for k in allowed_keys)
    if not is_valid:
        return False
    return api_key


async def validate_api_key_or_raise(
    authorization: str = Header(default="", alias="Authorization"),
) -> str:
    return await require_api_key(authorization)


def require_valid_api_key(api_key: str) -> str:
    """リクエストボディで受け取った API キーを検証し、無効なら 401 を送出する。

    ``validate_api_key_sync`` は例外を送出せず値を返すだけなので、
    呼び出し側で戻り値を捨てると検証が丸ごとスキップされてしまう。
    このラッパーは「検証して、無効なら例外を発生させる」-purpose 専用に用意している。
    ``api_key`` が空文字列 / None の場合は「検証しない（任意）」として素通しする。
    """
    if not api_key:
        return api_key
    if validate_api_key_sync(api_key) is False:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return api_key


def get_prompt_manager() -> Any:
    """FastAPI Depends 用の PromptManager プロバイダ。

    ``prompts.manager.PromptManager`` を遅延 import して返す。
    import 失敗時は None を返し、依存側でフォールバックできるようにする。
    """
    try:
        from prompts.manager import PromptManager

        return PromptManager()
    except Exception as e:  # noqa: BLE001
        logger.warning("PromptManager initialization failed: %s", e)
        return None


__all__ = [
    "get_current_user",
    "get_current_user_or_service_key",
    "get_prompt_manager",
    "oauth2_scheme",
    "require_admin_user",
    "require_admin_user_or_key",
    "require_api_key",
    "require_valid_api_key",
    "validate_api_key_or_raise",
    "validate_api_key_sync",
]
