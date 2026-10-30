import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.config import settings
from src.backend.database import get_async_db
from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.services.billing.stripe_client import StripeClient
from src.services.billing.credit_service import CreditService
from src.config.billing_plans import PLAN_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])


def _safe_redirect_url(candidate: str | None, default_path: str) -> str:
    """クライアント指定のリダイレクト先を FRONTEND_URL 配下に制限する。

    Stripe Checkout の success/cancel URL を任意に指定できると、決済後に
    攻撃者のフィッシングサイトへ飛ばす導線を作れる。絶対 URL は
    ``FRONTEND_URL`` と同一オリジンのみ許可し、相対パスは FRONTEND_URL で
    結合する。それ以外は既定パスへフォールバックする。
    """
    base = settings.FRONTEND_URL.rstrip("/")
    default = f"{base}{default_path}"
    if not candidate:
        return default
    candidate = candidate.strip()
    if not candidate:
        return default
    # 相対パス（"/billing/success" 等）はフロントエンド配下に結合する。
    if candidate.startswith("/") and not candidate.startswith("//"):
        return f"{base}{candidate}"
    if candidate == base or candidate.startswith(base + "/"):
        return candidate
    logger.warning("Rejected non-frontend redirect URL for Stripe session: %s", candidate)
    return default

@router.get("/plans", response_model=Dict[str, Any])
async def get_plans():
    """
    利用可能なプランと価格一覧を取得
    """
    # フロントエンドが期待する形式でプラン情報を返す
    plans = {}
    for plan_id, config in PLAN_CONFIG.items():
        plans[plan_id] = {
            "id": plan_id,
            "name": plan_id.capitalize(),
            "price_jpy": config["price_jpy"],
            "monthly_credits": config["monthly_credits"],
            "max_parallel_jobs": config["max_parallel_jobs"],
            "description": f"{config['monthly_credits']}クレジット/月"
        }
    return {"plans": plans}

@router.get("/balance", response_model=Dict[str, Any])
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    現在のユーザー残高とプラン情報を取得
    """
    credit_service = CreditService(db)
    balance = await credit_service.get_balance(current_user.id)

    return {
        "balance": balance,
        "plan_tier": current_user.plan_tier,
        "user_id": current_user.id
    }

@router.post("/create-checkout-session", response_model=Dict[str, str])
async def create_checkout_session(
    request: Dict[str, str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Stripe Checkout セッションを作成してURLを取得
    """
    price_id = request.get("price_id")
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="price_id is required"
        )

    success_url = _safe_redirect_url(request.get("success_url"), "/billing/success")
    cancel_url = _safe_redirect_url(request.get("cancel_url"), "/billing/cancel")

    try:
        checkout_url = StripeClient.create_checkout_session(
            user_id=current_user.id,
            user_email=current_user.email,
            price_id=price_id,
            success_url=success_url,
            cancel_url=cancel_url
        )
        return {"checkout_url": checkout_url}
    except Exception as e:
        logger.error("Failed to create checkout session: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )

@router.post("/create-portal-session", response_model=Dict[str, str])
async def create_portal_session(
    request: Dict[str, str],
    current_user: User = Depends(get_current_user)
):
    """
    Stripe Customer Portal セッションを作成してURLを取得
    """
    # ユーザーのStripe Customer IDを取得
    stripe_customer_id = current_user.stripe_customer_id
    if not stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe customer ID not found for user"
        )

    return_url = _safe_redirect_url(request.get("return_url"), "/billing")

    try:
        portal_url = StripeClient.create_customer_portal_session(
            stripe_customer_id=stripe_customer_id,
            return_url=return_url
        )
        return {"portal_url": portal_url}
    except Exception as e:
        logger.error("Failed to create portal session: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portal session"
        )


@router.get("/transactions", response_model=Dict[str, Any])
async def get_transactions(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    ユーザーのクレジット取引履歴を取得
    """
    from sqlalchemy import select, desc
    from src.backend.database.models_billing import CreditTransaction

    query = select(CreditTransaction).where(
        CreditTransaction.user_id == current_user.id
    ).order_by(desc(CreditTransaction.created_at)).limit(limit).offset(offset)

    result = await db.execute(query)
    transactions = result.scalars().all()

    # シリアライズ可能な形式に変換
    transaction_list = []
    for tx in transactions:
        transaction_list.append({
            "id": tx.id,
            "amount": tx.amount,
            "balance_after": tx.balance_after,
            "transaction_type": tx.transaction_type,
            "task_id": tx.task_id,
            "description": tx.description,
            "created_at": tx.created_at.isoformat() if tx.created_at else None
        })

    return {
        "transactions": transaction_list,
        "limit": limit,
        "offset": offset
    }
