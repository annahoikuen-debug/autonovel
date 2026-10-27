"""上級者エディタ用 API ルーターモジュール.

インラインAI（五感拡張・Show Don't Tell・リライト）、
GraphRAG 専属AI編集者（Ask Bible・矛盾診断）、
Next Beats 3バリエーション分岐生成エンドポイントを提供。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.backend.auth import get_current_user
from src.backend.database import get_db
from src.backend.database.models import User
from src.backend.rate_limit import generate_limiter
from src.models.editor import (
    AskBibleRequest,
    AskBibleResponse,
    AssistRequest,
    AssistResponse,
    ConsistencyAuditRequest,
    ConsistencyAuditResponse,
    NextBeatsRequest,
    NextBeatsResponse,
    AuditFastHybridRequest,
)
from src.models.unified_audit import UnifiedAuditReport
from src.services.editor_assist_service import EditorAssistService
from src.services.editorial_assistant_service import EditorialAssistantService
from src.services.next_beats_service import NextBeatsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/editor", tags=["editor"])

# サービスインスタンスの初期化
assist_service = EditorAssistService()
editorial_service = EditorialAssistantService()
next_beats_service = NextBeatsService()


@router.post("/assist", response_model=AssistResponse)
async def assist_content(
    req: AssistRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AssistResponse:
    """選択テキストに対するインラインAI推敲・五感描写拡張・Show Don't Tell・トーン変換"""
    await generate_limiter.check(request)
    try:
        return await assist_service.assist(req)
    except Exception as e:
        logger.error(f"Error in assist_content endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask-bible", response_model=AskBibleResponse)
async def ask_bible(
    req: AskBibleRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AskBibleResponse:
    """GraphRAG（ベクトル検索 + ナレッジグラフ）を活用した世界観設定資料・過去章 Q&A"""
    await generate_limiter.check(request)
    try:
        return await editorial_service.ask_bible(session, req)
    except Exception as e:
        logger.error(f"Error in ask_bible endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit-consistency", response_model=ConsistencyAuditResponse)
async def audit_consistency(
    req: ConsistencyAuditRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConsistencyAuditResponse:
    """執筆中の本文と設定情報とのリアルタイム矛盾診断"""
    await generate_limiter.check(request)
    try:
        return await editorial_service.audit_consistency(session, req)
    except Exception as e:
        logger.error(f"Error in audit_consistency endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit", response_model=UnifiedAuditReport)
async def audit_fast_hybrid(
    req: AuditFastHybridRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> UnifiedAuditReport:
    """v5.0: 二層ハイブリッド監査（静的ルール解析＋定性判定）エンドポイント"""
    await generate_limiter.check(request)
    try:
        from src.agents.specialists.unified_auditor import UnifiedAuditor
        auditor = UnifiedAuditor()
        report = await auditor.audit(
            text=req.draft_text,
            character_profiles=req.character_profiles,
            plot_spec=req.plot_spec,
        )
        return report
    except Exception as e:
        logger.error(f"Error in audit_fast_hybrid: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/next-beats", response_model=NextBeatsResponse)
async def generate_next_beats(
    req: NextBeatsRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> NextBeatsResponse:
    """直前までの本文から、王道・サスペンス・心情の3つの展開バリエーションを並列生成"""
    await generate_limiter.check(request)
    try:
        return await next_beats_service.generate_three_beats(req)
    except Exception as e:
        logger.error(f"Error in generate_next_beats endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
