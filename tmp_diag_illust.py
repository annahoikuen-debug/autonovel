"""一時診断スクリプト: batch エンドポイントの所有権検証経路を確認する。"""
import asyncio
import sys
from unittest.mock import MagicMock

import src.backend.routers.illustrations as m


class F:
    illustration_agent = MagicMock()

    async def execute(self, **kw):
        return {}


async def check():
    try:
        r = await m.batch_generate_illustrations(
            {"book_id": 1, "settings": {}},
            current_user=MagicMock(role="admin"),
            workflow=F(),
        )
        print("OK:", r)
    except Exception as e:
        import traceback

        traceback.print_exc()


asyncio.run(check())
