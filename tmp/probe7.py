import sys, asyncio
sys.path.insert(0, '.')
from unittest.mock import MagicMock, AsyncMock
from src.services.book_score_service import BookScoreCalculator

state = {"plot": None, "chapter": None, "illustration": None, "bible": None, "audit": ["A"]}

def make_result(value):
    res = MagicMock()
    sc = res.scalars.return_value
    if isinstance(value, list):
        sc.all.return_value = value
        sc.first.return_value = value[0] if value else None
    else:
        sc.first.return_value = value
        sc.all.return_value = [value] if value is not None else []
    return res

async def _execute(stmt):
    s = str(stmt)
    print('STMT TABLE:', s[:80])
    if "plots" in s: return make_result(state["plot"])
    if "chapters" in s: return make_result(state["chapter"])
    if "illustrations" in s: return make_result(state["illustration"])
    if "bibles" in s: return make_result(state["bible"])
    return make_result(state["audit"])

repo = MagicMock()
repo.session = MagicMock()
repo.session.execute = AsyncMock(side_effect=_execute)
calc = BookScoreCalculator(config_path="nonexistent.yaml", repository=repo)
print(asyncio.run(calc._fetch_audit_report(1, 1)))
