import sys, asyncio
sys.path.insert(0, '.')
from unittest.mock import MagicMock, AsyncMock
from src.services.book_score_service import BookScoreCalculator
from src.backend.database.models import Plot as P, Chapter as C, Illustration as I, Bible as B, AuditIssue as A
from sqlalchemy import select
for m, f in [(P,'ep_num'),(P,'end_ep'),(C,'ep_num'),(C,'tension'),(I,'episode_number'),(B,'settings'),(A,'ep_num'),(A,'category'),(A,'severity'),(A,'description')]:
    print(m.__tablename__, f, hasattr(m, f))
print(str(select(A).where(A.book_id==1, A.ep_num==1).order_by(A.id.desc()))[:120])
