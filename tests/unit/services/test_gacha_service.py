"""GachaService のフォールバック経路テスト（Plan Q7 Step8）。

LLM が常に JSONDecodeError を返す場合に、到達不能 fallback 削除後も
内側の fallback（``if attempt == max_retries``）で全案が生成されることを検証する。

注意: ``except (ValidationError, json.JSONDecodeError, BaseException)`` が
``CancelledError`` を握りつぶす点は pre-existing として別判断（Plan Q7 Step8 の
コミットメッセージに開示済み）。本テストでは対象外とする。
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities.easy_mode import GachaPlanType, GachaRequest
from src.services.gacha_service import GachaService


def _make_service() -> tuple[GachaService, MagicMock]:
    """LLM が常に JSONDecodeError を投げる GachaService と、その mock_llm を返す。

    DB 保存（_save_gacha_plans_db / _save_review_session）は AsyncMock で差し替え、
    実 DB への依存を排除する。
    """
    mock_llm = MagicMock()
    mock_llm.generate_json = AsyncMock(
        side_effect=json.JSONDecodeError("bad json", "doc", 0)
    )
    service = GachaService(llm_service=mock_llm, db=MagicMock())
    service._save_gacha_plans_db = AsyncMock()
    service._save_review_session = AsyncMock()
    return service, mock_llm


@pytest.mark.asyncio
async def test_generate_plans_fallback_on_llm_failure():
    """LLM が常に JSONDecodeError を返す場合、全案がフォールバックで生成されること。"""
    service, mock_llm = _make_service()

    request = GachaRequest(genre="異世界ファンタジー", keywords=["魔法", "冒険"])
    response = await service.generate_plans(request)

    # 3案（王道・変化球・ダーク）が返ること
    assert len(response.plans) == 3
    # 全案がフォールバック（LLM 生成ではない固定テンプレート）
    for plan in response.plans:
        assert plan.title == f"異世界ファンタジー：{plan.plan_type.value}の物語"
        assert plan.protagonist_summary == "個性的で魅力的な主人公"
    # plan_type が 3 種そろっていること
    assert {p.plan_type for p in response.plans} == set(GachaPlanType)
    # LLM が 3案 × リトライ回数分呼ばれていること（フォールバックに到達した証左）
    assert mock_llm.generate_json.await_count == 3 * 3
