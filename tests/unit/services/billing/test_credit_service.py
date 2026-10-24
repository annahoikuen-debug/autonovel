import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.billing.credit_service import CreditService


@pytest.mark.asyncio
async def test_credit_service_flow():
    mock_session = AsyncMock(spec=AsyncSession)

    # Mocking get_balance and db execution
    mock_execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = 100
    mock_execute.return_value = mock_result
    mock_session.execute = mock_execute

    service = CreditService(mock_session)

    # Test balance
    balance = await service.get_balance(1)
    assert balance == 100


@pytest.mark.asyncio
async def test_deduct_credits_flow():
    mock_session = AsyncMock(spec=AsyncSession)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 1

    mock_balance_result = MagicMock()
    mock_balance_result.scalar_one_or_none.return_value = 70

    mock_session.execute.side_effect = [
        mock_update_result,  # UPDATE
        mock_balance_result,  # get_balance
    ]

    service = CreditService(mock_session)

    result = await service.deduct_credits(1, 30, "test", "Deduct test")
    assert result is True
    assert mock_update_result.rowcount == 1


@pytest.mark.asyncio
async def test_grant_credits_flow():
    mock_session = AsyncMock(spec=AsyncSession)

    mock_update_result = MagicMock()
    mock_update_result.rowcount = 1

    mock_balance_result = MagicMock()
    mock_balance_result.scalar_one_or_none.return_value = 150

    mock_session.execute.side_effect = [
        mock_update_result,  # UPDATE
        mock_balance_result,  # get_balance
    ]

    service = CreditService(mock_session)

    new_balance = await service.grant_credits(1, 50, "test", "Grant test")
    assert new_balance == 150

    with pytest.raises(ValueError, match="付与額は正の整数である必要があります"):
        await service.grant_credits(1, 0, "test", "Invalid")
