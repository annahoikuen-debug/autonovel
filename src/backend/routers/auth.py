from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.backend.config import settings
from src.backend.database import get_async_db
from src.backend.database.models import User
from src.models.user import UserRegisterRequest, UserLoginRequest, TokenResponse, UserProfileResponse
from src.backend.security.password import hash_password, verify_password
from src.backend.security.jwt import create_access_token, create_refresh_token, decode_token
from src.backend.security.token_denylist import is_revoked, revoke as revoke_token
from src.backend.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _extract_bearer(authorization: str) -> str:
    """``Authorization`` ヘッダーから Bearer トークン本文を取り出す。"""
    if not authorization:
        return ""
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return authorization.strip()

@router.post("/register", response_model=UserProfileResponse)
async def register(request: UserRegisterRequest, db: AsyncSession = Depends(get_async_db)):
    # パスワード強度チェック：最低 8 文字以上
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="パスワードは 8 文字以上で設定してください",
        )

    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="既に登録されているメールアドレスです")

    user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        display_name=request.display_name,
        credits=50
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

def _issue_tokens(user: User) -> dict:
    """ユーザー向けのアクセストークンとリフレッシュトークンを発行する。"""
    return {
        "access_token": create_access_token(user.id, role=user.role),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        # 実際のトークン TTL は ACCESS_TOKEN_EXPIRE_MINUTES に決まるため、
        # ここでハードコードせず設定値から導出する（ずれるとクライアントが
        # 切替タイミングを誤って途中ログアウトする）。
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLoginRequest, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalars().first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが正しくありません")

    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    authorization: str = Header(default="", alias="Authorization"),
    db: AsyncSession = Depends(get_async_db),
):
    """リフレッシュトークンから新しいアクセストークンを発行する。

    リフレッシュトークンは `Authorization: Bearer <refresh_token>` で受け取る
    （クエリ文字列に置くとアクセスログへ平文で残るため）。
    ログインが既に同トークンを発行しており、GlobalAuthMiddleware の公開パスにも
    登録されているため、未提供の状態ではクライアントがトークンを更新できない。
    """
    token = _extract_bearer(authorization)
    payload = decode_token(token, expected_type="refresh") if token else None
    if payload is None:
        raise HTTPException(status_code=401, detail="無効なリフレッシュトークンです")
    # ログアウトで失効させたリフレッシュトークンは新しいアクセストークンを発行しない。
    if await is_revoked(payload.get("jti")):
        raise HTTPException(status_code=401, detail="無効なリフレッシュトークンです")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="無効なトークンペイロードです")

    user_id = int(sub) if isinstance(sub, (int, str)) and str(sub).isdigit() else sub
    user = await db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="ユーザーが存在しないか、無効化されています")

    return _issue_tokens(user)

@router.get("/me", response_model=UserProfileResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


class LogoutRequest(BaseModel):
    """ログアウト時に併せて失効させるリフレッシュトークン (任意)。"""

    refresh_token: str | None = None


@router.post("/logout")
async def logout(
    authorization: str = Header(default="", alias="Authorization"),
    body: LogoutRequest | None = None,
):
    """提示されたアクセストークンを失効させる (ログアウト)。

    JWT はステートレスなので発行後は `exp` まで有効なまま残る。本エンドポイントは
    そのトークンの ``jti`` を失効リストへ追加し、それ以降は署名が正しくても
    ``GlobalAuthMiddleware`` / ``get_current_user`` が 401 を返すようにする。

    認証は必須 (公開パスではない)。失効できるのは「正当な署名を持つトークンを
    所持している場合」だけで、未認証の呼び出し側は何も失効させられない。

    リフレッシュトークンをクライアントが保持している場合は ``body.refresh_token``
    で併せて失効できる。これを怠るとログアウト後もリフレッシュ経由で
    アクセストークンを取り直せてしまう。
    """
    token = _extract_bearer(authorization)
    payload = decode_token(token, expected_type="access") if token else None
    if payload is None:
        raise HTTPException(status_code=401, detail="無効なトークンです")

    # ミドルウェアは通っているので通常は到達しないが、二重の防御として
    # 既に失効済みなら何もしない (冪等)。
    if not await is_revoked(payload.get("jti")):
        await revoke_token(payload.get("jti"), payload.get("exp"))

    if body and body.refresh_token:
        refresh_payload = decode_token(body.refresh_token, expected_type="refresh")
        if refresh_payload is not None and not await is_revoked(refresh_payload.get("jti")):
            await revoke_token(refresh_payload.get("jti"), refresh_payload.get("exp"))

    return {"message": "ログアウトしました"}
