import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.billing.credit_service import CreditService, InsufficientCreditsError
from src.backend.database.models import User

@pytest.mark.asyncio
async def test_credit_service_flow(db_session: AsyncSession):
    # Setup: Create a user
    user = User(id=1, email="test@example.com", credits=100)
    db_session.add(user)
    await db_session.commit()
    
    service = CreditService(db_session)
    
    # Test balance
    assert await service.get_balance(1) == 100
    
    # Test grant
    new_balance = await service.grant_credits(1, 50, "test", "Grant test")
    assert new_balance == 150
    assert await service.get_balance(1) == 150
    
    # Test deduct
    await service.deduct_credits(1, 30, "test", "Deduct test")
    assert await service.get_balance(1) == 120
    
    # Test insufficient credits
    with pytest.raises(InsufficientCreditsError):
        await service.deduct_credits(1, 200, "test", "Fail test")
        
    # Test text/illustration deduction
    await service.deduct_credits_for_text_writing(1)
    assert await service.get_balance(1) == 119
    
    await service.deduct_credits_for_illustration(1)
    assert await service.get_balance(1) == 114
