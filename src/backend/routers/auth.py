from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.backend.config import settings
from src.backend.database import get_async_db
from src.backend.database.models import User
from src.models.user import UserRegisterRequest, UserLoginRequest, TokenResponse, UserProfileResponse
from src.backend.security.password import hash_password, verify_password
from src.backend.security.jwt import create_access_token, create_refresh_token, decode_token
from src.backend.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=UserProfileResponse)
async def register(request: UserRegisterRequest, db: AsyncSession = Depends(get_async_db)):
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
        "access_token": create_access_token(user.id, user.role),
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
    token = authorization[7:].strip() if authorization.startswith("Bearer ") else authorization.strip()
    payload = decode_token(token, expected_type="refresh") if token else None
    if payload is None:
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
