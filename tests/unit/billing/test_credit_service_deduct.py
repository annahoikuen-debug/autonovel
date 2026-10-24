"""クレジット減算のテスト: 残高不足・二重消費防止"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.billing.credit_service import CreditService, InsufficientCreditsError


@pytest.mark.asyncio
async def test_insufficient_credits_raises_error():
    """残高不足時に InsufficientCreditsError が発生し、残高がマイナスにならないことをテスト"""
    mock_session = AsyncMock(spec=AsyncSession)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 0

    mock_select_result = MagicMock()
    mock_select_result.scalar_one_or_none.return_value = 1  # user exists

    mock_session.execute.side_effect = [
        mock_update_result,  # First call: UPDATE
        mock_select_result,  # Second call: SELECT User.id
    ]

    credit_service = CreditService(mock_session)

    async def mock_get_balance(user_id):
        return 5

    credit_service.get_balance = mock_get_balance

    with pytest.raises(InsufficientCreditsError) as exc_info:
        await credit_service.deduct_credits(user_id=1, amount=10, transaction_type="test", description="Test deduction")

    assert "Insufficient credits" in str(exc_info.value)
    assert "Required: 10" in str(exc_info.value)
    assert "Available: 5" in str(exc_info.value)


@pytest.mark.asyncio
async def test_user_not_found_raises_error():
    """存在しないユーザーでエラーになる"""
    mock_session = AsyncMock(spec=AsyncSession)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 0

    mock_select_result = MagicMock()
    mock_select_result.scalar_one_or_none.return_value = None  # user not found

    mock_session.execute.side_effect = [
        mock_update_result,
        mock_select_result,
    ]

    credit_service = CreditService(mock_session)

    with pytest.raises(ValueError) as exc_info:
        await credit_service.deduct_credits(
            user_id=999, amount=5, transaction_type="test", description="User not found"
        )

    assert "ユーザーが見つかりません" in str(exc_info.value)


@pytest.mark.asyncio
async def test_zero_amount_deduction():
    """消費額0の場合はTrueを返す（エラーにしない）"""
    mock_session = AsyncMock(spec=AsyncSession)
    credit_service = CreditService(mock_session)

    result = await credit_service.deduct_credits(
        user_id=1, amount=0, transaction_type="test", description="Zero deduction"
    )

    assert result is True
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_negative_amount_raises_error():
    """負の消費額はエラーになる"""
    mock_session = AsyncMock(spec=AsyncSession)
    credit_service = CreditService(mock_session)

    with pytest.raises(ValueError) as exc_info:
        await credit_service.deduct_credits(
            user_id=1, amount=-5, transaction_type="test", description="Negative deduction"
        )

    assert "消費額は0以上である必要があります" in str(exc_info.value)


@pytest.mark.asyncio
async def test_deduct_credits_for_text_writing():
    """テキスト執筆用クレジット消費メソッドのテスト - 定数 COST_PER_EPISODE が使用されることを確認"""
    mock_session = AsyncMock(spec=AsyncSession)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 1

    mock_balance_result = MagicMock()
    mock_balance_result.scalar_one_or_none.return_value = 9

    mock_session.execute.side_effect = [
        mock_update_result,  # UPDATE
        mock_balance_result,  # get_balance (first)
        mock_balance_result,  # get_balance (second after transaction)
    ]

    async def mock_get_balance(user_id):
        return 9

    credit_service = CreditService(mock_session)
    credit_service.get_balance = mock_get_balance

    result = await credit_service.deduct_credits_for_text_writing(user_id=1)

    assert result is True


@pytest.mark.asyncio
async def test_deduct_credits_for_illustration():
    """画像生成用クレジット消費メソッドのテスト - 定数 COST_PER_ILLUSTRATION が使用されることを確認"""
    mock_session = AsyncMock(spec=AsyncSession)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 1

    mock_balance_result = MagicMock()
    mock_balance_result.scalar_one_or_none.return_value = 5

    mock_session.execute.side_effect = [
        mock_update_result,
        mock_balance_result,
        mock_balance_result,
    ]

    async def mock_get_balance(user_id):
        return 5

    credit_service = CreditService(mock_session)
    credit_service.get_balance = mock_get_balance

    result = await credit_service.deduct_credits_for_illustration(user_id=1)

    assert result is True


@pytest.mark.asyncio
async def test_deduct_credits_success():
    """正常なクレジット減算フローのテスト"""
    mock_session = AsyncMock(spec=AsyncSession)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 1

    mock_balance_result = MagicMock()
    mock_balance_result.scalar_one_or_none.return_value = 5

    mock_session.execute.side_effect = [
        mock_update_result,  # UPDATE
        mock_balance_result,  # get_balance (first)
        mock_balance_result,  # get_balance (second after transaction)
    ]

    async def mock_get_balance(user_id):
        return 5

    credit_service = CreditService(mock_session)
    credit_service.get_balance = mock_get_balance

    result = await credit_service.deduct_credits(
        user_id=1, amount=5, transaction_type="consumption", description="Normal deduction"
    )

    assert result is True


# ============================================================================
# 冪等控除: 同一 (task_id, transaction_type) では二重消費しない
# ============================================================================


@pytest.mark.asyncio
async def test_deduct_credits_is_idempotent_for_same_task():
    """同一 (task_id, transaction_type) で2回控除しても残高・台帳は1回分だけ減る。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.backend.database.models import Base, User
    from src.backend.database.models_billing import CreditTransaction

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        async with engine.begin() as conn:
            # User.tenant_id が tenants を FK 参照するため、部分作成だと
            # INSERT 時に `no such table: main.tenants` になる。全テーブルを作成する。
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn))
        local_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with local_session() as session:
            session.add(
                User(
                    id=9001,
                    email="idem@example.com",
                    hashed_password="x",
                    display_name="idem",
                    credits=50,
                )
            )
            await session.commit()

            credit_service = CreditService(session)
            await credit_service.deduct_credits(
                user_id=9001,
                amount=10,
                transaction_type="consumption",
                description="1回目",
                task_id="task-idem-1",
            )
            assert await credit_service.get_balance(9001) == 40

            # リトライ / リプレイ: 同一キーでは二重控除しない (冪等)
            await credit_service.deduct_credits(
                user_id=9001,
                amount=10,
                transaction_type="consumption",
                description="2回目 (リトライ)",
                task_id="task-idem-1",
            )
            assert await credit_service.get_balance(9001) == 40

            rows = (
                (
                    await session.execute(
                        select(CreditTransaction.id).where(
                            CreditTransaction.task_id == "task-idem-1",
                            CreditTransaction.transaction_type == "consumption",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1

            # transaction_type が異なればキーも別なので、従来どおり控除される
            await credit_service.deduct_credits(
                user_id=9001,
                amount=5,
                transaction_type="illustration_batch",
                description="別種別",
                task_id="task-idem-1",
            )
            assert await credit_service.get_balance(9001) == 35
    finally:
        await engine.dispose()


def test_sync_deduct_credits_is_idempotent_for_same_task(db_session):
    """Huey 同期版 ``_sync_deduct_credits`` も同一キーで二重控除しない。"""
    from sqlalchemy import select

    from src.backend.database.models import CreditTransaction, User
    from src.backend.tasks.generation_tasks import _sync_deduct_credits

    db_session.add(
        User(
            id=9002,
            email="idem-sync@example.com",
            hashed_password="x",
            display_name="idem-sync",
            credits=50,
        )
    )
    db_session.commit()

    _sync_deduct_credits(user_id=9002, amount=10, task_id="task-sync-1", description="1回目")
    # Huey リトライでの再実行: 同一 (task_id, transaction_type) ならスキップされる
    _sync_deduct_credits(user_id=9002, amount=10, task_id="task-sync-1", description="2回目 (リトライ)")

    balance = db_session.execute(select(User.credits).where(User.id == 9002)).scalar_one()
    assert balance == 40

    rows = (
        db_session.execute(select(CreditTransaction.id).where(CreditTransaction.task_id == "task-sync-1"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
