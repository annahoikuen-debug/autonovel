import logging
import stripe
from src.backend.config import settings

logger = logging.getLogger(__name__)


def _ensure_stripe_api_key() -> None:
    """Stripe API キーを動的に設定する。

    モジュール読み込み時に空文字で ``stripe.api_key`` を設定すると、
    設定ミスに気づかず Stripe API 呼び出しが認証エラーになる。
    各呼び出し直前に settings から取得し、未設定なら明示的エラーを送出する。
    """
    api_key = getattr(settings, "STRIPE_SECRET_KEY", None) or ""
    if not api_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not configured. Set it in .env or environment."
        )
    stripe.api_key = api_key


class StripeClient:
    """Stripe SDKラッパークラス"""

    @staticmethod
    def create_checkout_session(
        user_id: int,
        user_email: str,
        price_id: str,
        success_url: str,
        cancel_url: str
    ) -> str:
        """
        Stripe Checkout Sessionを生成してURLを返す

        Args:
            user_id: ユーザーID
            user_email: ユーザーのメールアドレス
            price_id: Stripe Price ID
            success_url: 成功時のリダイレクトURL
            cancel_url: キャンセル時のリダイレクトURL

        Returns:
            Checkout Session URL
        """
        _ensure_stripe_api_key()
        try:
            # まずStripe Customerを取得または作成
            customer = StripeClient._get_or_create_customer(user_id, user_email)

            # Checkout Sessionを作成
            session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_id': str(user_id)
                }
            )

            return session.url
        except stripe.error.StripeError as e:
            logger.error("Stripe API error creating checkout session: %s", e, exc_info=True)
            raise RuntimeError(f"Failed to create checkout session: {e}") from e
        except Exception as e:
            logger.error("Unexpected error creating checkout session: %s", e, exc_info=True)
            raise

    @staticmethod
    def create_customer_portal_session(stripe_customer_id: str, return_url: str) -> str:
        """
        Stripe Customer Portalセッションを生成してURLを返す

        Args:
            stripe_customer_id: Stripe Customer ID
            return_url: ポータルから戻るURL

        Returns:
            Customer Portal Session URL
        """
        _ensure_stripe_api_key()
        try:
            session = stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=return_url,
            )
            return session.url
        except stripe.error.StripeError as e:
            logger.error("Stripe API error creating customer portal session: %s", e, exc_info=True)
            raise RuntimeError(f"Failed to create customer portal session: {e}") from e
        except Exception as e:
            logger.error("Unexpected error creating customer portal session: %s", e, exc_info=True)
            raise

    @staticmethod
    def _get_or_create_customer(user_id: int, user_email: str):
        """
        ユーザーのStripe Customerを取得または作成

        データベースから stripe_customer_id を取得し、存在しない場合のみ
        新規 Stripe Customer を作成する。重複顧客の作成を防ぐため、
        メタデータの user_id で既存顧客を特定する。

        Args:
            user_id: ユーザーID
            user_email: ユーザーのメールアドレス

        Returns:
            Stripe Customer オブジェクト
        """
        _ensure_stripe_api_key()
        try:
            # メタデータの user_id で既存顧客を検索（重複防止）
            customers = stripe.Customer.list(
                limit=100,
                metadata={'user_id': str(user_id)}
            )
            if customers.data:
                return customers.data[0]

            # メールで検索（フォールバック）
            customers_by_email = stripe.Customer.list(email=user_email, limit=1)
            if customers_by_email.data:
                return customers_by_email.data[0]

            # 新規顧客作成
            customer = stripe.Customer.create(
                email=user_email,
                metadata={
                    'user_id': str(user_id)
                }
            )
            return customer
        except stripe.error.StripeError as e:
            logger.error("Stripe API error getting or creating customer: %s", e, exc_info=True)
            raise RuntimeError(f"Failed to get or create customer: {e}") from e
        except Exception as e:
            logger.error("Unexpected error getting or creating customer: %s", e, exc_info=True)
            raise
