"""
40話ビートシート取得・編集APIエンドポイント
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.auth import get_current_user
from src.backend.database import get_db
from src.backend.database.models import Book, Plot, User
from src.backend.security.owner_guard import verify_book_ownership_sync

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/commercial/planning",
    tags=["commercial-planning"],
    dependencies=[Depends(get_current_user)],
)


class BeatSheetItem(BaseModel):
    ep_num: int
    phase: str
    mission: str
    tension_target: float
    visual_scene_focus: str


class BeatSheetResponse(BaseModel):
    items: List[BeatSheetItem]


class BeatSheetGenerateRequest(BaseModel):
    book_id: Optional[int] = None
    title: str
    synopsis: str
    genre: str = "fantasy"
    target_episodes: int = 40
    # STORY_SPINE: 構造テンプレートの指定（既定値は既存挙動と同じ exile_rise）
    pattern_key: str = "exile_rise"
    length_key: str = "web_volume"
    market_key: str = "web"


@router.get("/{book_id}", response_model=BeatSheetResponse)
async def get_beat_sheet(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    書籍IDに紐づく40話ビートシートを取得する。
    存在しない場合は404を返す。
    """
    verify_book_ownership_sync(book_id, current_user, db)
    try:
        stmt = select(Plot).where(Plot.book_id == book_id).order_by(Plot.ep_num)
        result = db.execute(stmt)
        plots = result.scalars().all()

        if not plots:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Beat sheet for book_id {book_id} not found",
            )

        items = [
            BeatSheetItem(
                ep_num=p.ep_num,
                phase=p.current_chain_phase or "Setup",
                mission=p.summary or p.title or f"第{p.ep_num}話",
                tension_target=float(p.target_tension if p.target_tension is not None else (p.tension or 50) / 100.0),
                visual_scene_focus=p.one_line_summary or p.title or "",
            )
            for p in plots
        ]
        return BeatSheetResponse(items=items)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get beat sheet: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve beat sheet",
        )


@router.post("/generate", response_model=BeatSheetResponse)
async def generate_beat_sheet(
    request: BeatSheetGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    タイトルとあらすじから40話ビートシートを生成し、データベースに保存する。
    """
    try:
        book_id = request.book_id
        if book_id is None:
            # 新規ブックを仮作成
            owner_id = getattr(current_user, "id", None)
            if owner_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="書籍を作成するには認証が必要です",
                )
            book = Book(
                title=request.title,
                genre=request.genre,
                synopsis=request.synopsis,
                user_id=owner_id,
            )
            db.add(book)
            db.commit()
            db.refresh(book)
            book_id = book.id
        else:
            # 既存作品を書き換えてよいのは所有者だけ。
            # これを確かめずに delete すると、他人のビートシートを全消去できてしまう。
            verify_book_ownership_sync(book_id, current_user, db)

        # 構造は STORY_SPINE が単一のソースになる。
        # 旧実装はここに 4 幕（起/承/転/結）をハードコードしており、
        # COMMERCIAL_40EP_BEATS（7 phase）と真逆に矛盾していた。
        from src.services.spine_resolver import resolve_spine

        spine = resolve_spine(
            request.pattern_key, request.length_key, request.market_key,
            request.target_episodes,
        )
        items: List[BeatSheetItem] = []

        # 既存プロットがあれば一旦削除して再生成
        db.query(Plot).filter(Plot.book_id == book_id).delete()

        for ep in range(1, request.target_episodes + 1):
            beat = spine.at(ep)
            phase = beat.label if beat else "展開"
            tension = beat.tension if beat else 0.5

            title = f"{request.title} 第{ep}話"
            mission = beat.duty if beat else "物語を着実に進行させる。"
            visual_focus = (
                f"第{ep}話 {phase}の象徴的シーン演出"
                if beat
                else f"第{ep}話 象徴的シーン演出"
            )

            plot_record = Plot(
                book_id=book_id,
                branch_id=1,
                ep_num=ep,
                title=title,
                summary=mission,
                one_line_summary=visual_focus,
                current_chain_phase=phase,
                tension=int(tension * 100),
                target_tension=round(tension, 2),
                status="planned",
            )
            db.add(plot_record)

            items.append(
                BeatSheetItem(
                    ep_num=ep,
                    phase=phase,
                    mission=mission,
                    tension_target=round(tension, 2),
                    visual_scene_focus=visual_focus,
                )
            )

        db.commit()
        return BeatSheetResponse(items=items)
    except HTTPException:
        # 所有権検証の 403/404 を 500 に潰さない。
        db.rollback()
        raise
    except Exception as e:
        logger.error("Failed to generate beat sheet: %s", e, exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate beat sheet",
        )