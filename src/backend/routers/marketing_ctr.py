"""
マーケティングCTR APIルーター
PLAN 01: タイトル＆あらすじCTR爆発エンジン
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src.agents.marketing import MarketingAgent
from src.backend.auth import get_prompt_manager
from src.backend.rate_limit import generate_limiter
from src.models.marketing_ctr import ViralTitleRequest, ViralTitleResponse

from src.services.llm.factory import get_llm_adapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketing", tags=["marketing_ctr"])


@router.post("/viral-titles", response_model=ViralTitleResponse)
async def generate_viral_titles(
    request: ViralTitleRequest,
    http_request: Request,
    prompt_manager: Any = Depends(get_prompt_manager),
) -> ViralTitleResponse:
    """カクヨムCTR最大化タイトル候補30〜50案を生成・採点し、上位推薦案とあらすじを返す。"""
    # 429 を `except Exception` で 500 に変換しないため、try の外で検査する。
    await generate_limiter.check(http_request)
    try:
        llm = get_llm_adapter()
        agent = MarketingAgent(llm=llm, prompt_manager=prompt_manager)
        return await agent.generate_viral_title_pack(request)
    except Exception as e:
        logger.exception("Failed to generate viral titles: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
