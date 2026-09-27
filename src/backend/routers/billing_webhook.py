import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.config import settings
from src.backend.database import get_async_db
from src.backend.database.models import User
from src.backend.database.models_billing import StripeWebhookEvent
from src.config.billing_plans import get_credits_for_price_id, get_tier_for_price_id
from src.services.billing.credit_service import CreditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing/webhook", tags=["billing-webhook"])

# Webhook署名の検証用エンドポイントシークレット
WEBHOOK_SECRET = getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or ""

# 署名検証なしでペイロードを受け付けてよい環境（ローカル検証専用）
# 本番・ステージングでは必ず STRIPE_WEBHOOK_SECRET を設定すること。
SIGNATURE_OPTIONAL_ENVS: frozenset[str] = frozenset({"local", "testing", "development"})


def _signature_verification_optional() -> bool:
    """署名検証を省略してよい環境かどうかを返す。"""
    if WEBHOOK_SECRET:
        return False
    return str(getattr(settings, "APP_ENV", "")).lower() in SIGNATURE_OPTIONAL_ENVS


@router.post("")
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_async_db),
):
    """Stripe Webhookを受信して安全・非同期かつべき等に処理する。"""
    payload = await request.body()

    if not _signature_verification_optional():
        # 署名シークレット未設定 かつ 本番系環境 は 500 で即時拒否する
        # （これまで 200 を返していたため、攻撃者がクレジットを偽装付与できていた）
        if not WEBHOOK_SECRET:
            logger.error("STRIPE_WEBHOOK_SECRET is required outside local/testing environments!")
            raise HTTPException(
                status_code=500, detail="Server configuration error: missing webhook secret"
            )

    try:
        if WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, WEBHOOK_SECRET
            )
        else:
            # ローカル検証環境のみで、署名検証を省略して JSON を直接解釈する
            import json
            event = json.loads(payload)
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")

    event_id = event.get("id")
    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})

    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event ID")

    # べき等性チェック: 既に処理済みのイベントなら即座に 200 OK を返却
    existing_event = await db.get(StripeWebhookEvent, event_id)
    if existing_event:
        if existing_event.status == "processed":
            logger.info(f"Stripe event {event_id} already processed. Skipping duplicate.")
            return {"status": "already_processed", "event_id": event_id}
        elif existing_event.status == "processing":
            # 処理中イベントのタイムアウト判定 (10分以上経過していれば前回の処理クラッシュとみなして再試行)
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            created = existing_event.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created and (now - created) > timedelta(minutes=10):
                logger.warning(
                    f"Stripe event {event_id} was stuck in processing since {created}. Retrying processing."
                )
                existing_event.status = "processing"
                webhook_record = existing_event
            else:
                logger.info(f"Stripe event {event_id} is currently being processed. Skipping concurrent duplicate.")
                return {"status": "already_processing", "event_id": event_id}
        else:
            # status == "failed": 前回失敗したイベントの再試行
            logger.warning(f"Stripe event {event_id} previously failed. Retrying processing.")
            existing_event.status = "processing"
            webhook_record = existing_event
    else:
        # イベントを processing 状態で記録
        webhook_record = StripeWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            status="processing",
        )
        db.add(webhook_record)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # 同時並行リクエストで既にコミットされた場合
        return {"status": "already_processed", "event_id": event_id}

    try:
        if event_type == "checkout.session.completed":
            await _handle_checkout_session_completed(event_data, db, event_id=event_id)
        elif event_type == "invoice.payment_succeeded":
            await _handle_invoice_payment_succeeded(event_data, db, event_id=event_id)
        elif event_type == "customer.subscription.deleted":
            await _handle_customer_subscription_deleted(event_data, db)
        elif event_type == "customer.subscription.updated":
            await _handle_customer_subscription_updated(event_data, db)
        else:
            logger.info(f"Unhandled Stripe event type: {event_type}")

        webhook_record.status = "processed"
        await db.commit()
    except Exception as e:
        logger.error(f"Error handling Stripe webhook event {event_id}: {e}", exc_info=True)
        webhook_record.status = "failed"
        await db.commit()
        # 処理に失敗した場合は 5xx を返して Stripe に再試行させる。
        # 200 を返すとイベントが "成功" と記録され、永久に処理されなくなる。
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process Stripe event {event_id}",
        ) from e

    return {"status": "success", "event_id": event_id}


def _field(obj, key: str, default=None):
    """Stripe オブジェクト / dict のどちらからでもフィールドを取り出す。

    `stripe.Webhook.construct_event` 経由なら `StripeObject`、
    ローカル検証時の `json.loads` 経由なら素の `dict` が渡ってくるため、
    属性アクセスとキーアクセスの両方をここに集約する。
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    value = getattr(obj, key, None)
    if value is None:
        # StripeObject は Mapping なので get() も使える
        try:
            return obj.get(key, default)
        except Exception:  # noqa: BLE001 - get を持たないオブジェクトは既定値
            return default
    return value


def _dig(obj, *path: str, default=None):
    """`_field` を連続適用してネストしたフィールドを取り出す。"""
    current = obj
    for key in path:
        current = _field(current, key, default)
        if current is None:
            return default
    return current


async def _resolve_user(result) -> Optional[User]:
    """ResultからUserエンティティを安全に解決（同期・非同期モック両対応）"""
    user = result.scalar_one_or_none()
    if inspect.isawaitable(user):
        user = await user
    return user


async def _handle_checkout_session_completed(
    session: dict, db: AsyncSession, event_id: Optional[str] = None
):
    """Checkout Session完了時に初回クレジットを付与"""
    user_id = int(session.get("metadata", {}).get("user_id", 0))
    user = None
    if user_id == 0:
        stripe_customer_id = session.get("customer")
        if stripe_customer_id:
            result = await db.execute(
                select(User).where(User.stripe_customer_id == stripe_customer_id)
            )
            user = await _resolve_user(result)
            if user:
                user_id = user.id

    if user_id == 0:
        logger.warning(f"Could not determine user_id for checkout session: {session.get('id')}")
        return

    subscription_id = session.get("subscription")
    if not subscription_id:
        return

    # 同期ネットワーク呼び出しを非同期スレッドにオフロード
    subscription = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)

    if not user:
        result = await db.execute(select(User).where(User.id == user_id))
        user = await _resolve_user(result)
    if not user:
        logger.warning(f"User {user_id} not found in database")
        return

    credit_service = CreditService(db)

    credits_to_grant = 0
    if subscription.items.data:
        price_id = subscription.items.data[0].price.id
        credits_to_grant = get_credits_for_price_id(price_id)
        user.plan_tier = get_tier_for_price_id(price_id)

    if credits_to_grant > 0:
        if hasattr(user, "credits"):
            user.credits = (user.credits or 0) + credits_to_grant
        await credit_service.grant_credits(
            user_id=user_id,
            amount=credits_to_grant,
            transaction_type="monthly_grant",
            description=f"Initial credit grant for {getattr(subscription.plan, 'nickname', None) or 'subscription'}",
            task_id=f"stripe_evt_{event_id}" if event_id else None,
            auto_commit=False,
        )

    await _create_or_update_subscription_record(user, subscription, db)


async def _handle_invoice_payment_succeeded(
    invoice: dict, db: AsyncSession, event_id: Optional[str] = None
):
    """インボイス支払い成功時に月次クレジットを付与"""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    subscription = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)

    stripe_customer_id = subscription.customer
    if isinstance(stripe_customer_id, dict):
        stripe_customer_id = stripe_customer_id.get("id")

    result = await db.execute(
        select(User).where(User.stripe_customer_id == stripe_customer_id)
    )
    user = await _resolve_user(result)
    if not user:
        logger.warning(f"User with stripe_customer_id {stripe_customer_id} not found")
        return

    credit_service = CreditService(db)

    credits_to_grant = 0
    if subscription.items.data:
        price_id = subscription.items.data[0].price.id
        credits_to_grant = get_credits_for_price_id(price_id)
        user.plan_tier = get_tier_for_price_id(price_id)

    if credits_to_grant > 0:
        if hasattr(user, "credits"):
            user.credits = (user.credits or 0) + credits_to_grant
        await credit_service.grant_credits(
            user_id=user.id,
            amount=credits_to_grant,
            transaction_type="monthly_grant",
            description=f"Monthly credit grant for {getattr(subscription.plan, 'nickname', None) or 'subscription'}",
            task_id=f"stripe_evt_{event_id}" if event_id else None,
            auto_commit=False,
        )

    await _create_or_update_subscription_record(user, subscription, db)


async def _handle_customer_subscription_deleted(subscription, db: AsyncSession):
    """サブスクリプション削除時にフリープランにダウングレード"""
    stripe_customer_id = _field(subscription, "customer")
    if isinstance(stripe_customer_id, dict):
        stripe_customer_id = stripe_customer_id.get("id")

    result = await db.execute(
        select(User).where(User.stripe_customer_id == stripe_customer_id)
    )
    user = await _resolve_user(result)
    if not user:
        return

    user.plan_tier = "free"
    await db.flush()


async def _handle_customer_subscription_updated(subscription, db: AsyncSession):
    """サブスクリプション更新時に情報を同期"""
    stripe_customer_id = _field(subscription, "customer")
    if isinstance(stripe_customer_id, dict):
        stripe_customer_id = stripe_customer_id.get("id")

    result = await db.execute(
        select(User).where(User.stripe_customer_id == stripe_customer_id)
    )
    user = await _resolve_user(result)
    if not user:
        return

    await _create_or_update_subscription_record(user, subscription, db)


async def _create_or_update_subscription_record(user: User, subscription, db: AsyncSession):
    """サブスクリプションレコードを作成または更新"""
    from src.backend.database.models_billing import Subscription as SubscriptionModel

    result = await db.execute(
        select(SubscriptionModel).where(SubscriptionModel.user_id == user.id)
    )
    db_subscription = result.scalar_one_or_none()
    if inspect.isawaitable(db_subscription):
        db_subscription = await db_subscription

    price_id = _dig(subscription, "items", "data", default=None)
    price_id = "unknown"
    if isinstance(price_id, (list, tuple)) and price_id:
        first_item = price_id[0]
        nested = _field(first_item, "price")
        if nested is not None:
            resolved = _field(nested, "id")
            if resolved is not None:
                price_id = resolved
    tier = get_tier_for_price_id(price_id)
    period_end_val = _field(subscription, "current_period_end")
    if isinstance(period_end_val, (int, float)):
        period_end = datetime.fromtimestamp(period_end_val)
    else:
        period_end = datetime.now(timezone.utc)

    stripe_subscription_id = _field(subscription, "id")
    stripe_status = _field(subscription, "status")
    stripe_customer = _field(subscription, "customer")
    if isinstance(stripe_customer, dict):
        stripe_customer = stripe_customer.get("id")

    if db_subscription:
        db_subscription.stripe_subscription_id = stripe_subscription_id
        db_subscription.stripe_customer_id = stripe_customer
        db_subscription.plan_tier = tier
        db_subscription.status = stripe_status
        db_subscription.current_period_end = period_end
    else:
        new_subscription = SubscriptionModel(
            user_id=user.id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer,
            plan_tier=tier,
            status=stripe_status,
            current_period_end=period_end,
        )
        db.add(new_subscription)

    await db.flush()
