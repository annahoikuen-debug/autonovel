from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.backend.database import get_async_db
from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.config.billing_plans import TASK_CREDIT_COSTS


def require_credits(task_type: str):
    """Dependency that verifies user has sufficient credits and atomically deducts them.

    行ロック (SELECT ... FOR UPDATE) を取得したうえで残高をチェックし、
    クレジットを控除することで、同時リクエストによる二重控除を防止する。
    """

    async def dependency(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db),
    ):
        required = TASK_CREDIT_COSTS.get(task_type, 10)

        # 行ロックを取得して競合状態を防止する。
        # 同一ユーザーへの並行リクエストは、このトランザクションが
        # コミット/ロールバックするまで FOR UPDATE でブロックされる。
        stmt = select(User).where(User.id == current_user.id).with_for_update()
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ユーザーが見つかりません",
            )

        if db_user.credits < required:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error_code": "INSUFFICIENT_CREDITS",
                    "required": required,
                    "balance": db_user.credits,
                },
            )

        # クレジットを原子的に控除（flush で UPDATE を発行し、
        # 行ロックを保持したまま次の処理へ進める。コミットは呼び出し側の
        # トランザクション境界で行われる）。
        db_user.credits -= required
        await db.flush()

        return required

    return dependency