import json

from fastapi import APIRouter, Depends

from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.backend.security.owner_guard import verify_book_ownership
from src.backend.database import UnitOfWork
from src.core.container import AppContainer

router = APIRouter(tags=["misc"])


@router.get("/api/books/{book_id}/narrative_metrics", deprecated=True, tags=["metrics"])
async def get_narrative_metrics(
    book_id: int,
    branch_id: int = 1,
    ep_num: int | None = None,
    current_user: User = Depends(get_current_user),
):
    """[非推奨] 新path版 /api/narrative_metrics/{book_id}/{branch_id} を使用してください。"""
    try:
        from src.backend.database.repositories.narrative_metrics_repo import (
            NarrativeMetricRepository,
        )

        async with UnitOfWork(AppContainer.db()) as uow:
            # IDOR 防止: 作品の所有権を検証する
            await verify_book_ownership(book_id, current_user, uow)

        async with AppContainer.db().get_session() as session:
            repo = NarrativeMetricRepository(session)
            if ep_num is not None:
                trends = await repo.get_trend_metrics(book_id=book_id, branch_id=branch_id)
                data = [t for t in trends if t.get("ep_num") == ep_num]
            else:
                data = await repo.get_trend_metrics(book_id=book_id, branch_id=branch_id)
            return {"book_id": book_id, "branch_id": branch_id, "metrics": data}
    except Exception as e:
        from src.core.exceptions import AppError

        raise AppError(f"ナラティブメトリクスの取得に失敗: {e}", original=e)


@router.get("/api/bibles/{book_id}")
async def get_bible(
    book_id: int,
    current_user: User = Depends(get_current_user),
):
    async with UnitOfWork(AppContainer.db()) as uow:
        await verify_book_ownership(book_id, current_user, uow)
        b = await uow.bible.get_latest_bible(book_id)
    if not b:
        return {}
    return {
        "id": b.id,
        "book_id": b.book_id,
        "settings": json.loads(b.settings or "{}") if isinstance(b.settings, str) else b.settings,
        "revealed": json.loads(b.revealed or "{}") if isinstance(b.revealed, str) else b.revealed,
        "version": b.version,
    }


@router.get("/api/optimization_history/{book_id}")
async def get_opt_history(
    book_id: int,
    current_user: User = Depends(get_current_user),
):
    async with UnitOfWork(AppContainer.db()) as uow:
        await verify_book_ownership(book_id, current_user, uow)
        history = await uow.misc.get_optimization_history(book_id)
    return [
        {
            "id": h.id,
            "report_json": json.loads(h.report_json)
            if isinstance(h.report_json, str)
            else h.report_json,
            "created_at": h.created_at,
        }
        for h in history
    ]


@router.get("/api/narrative_metrics/{book_id}/{branch_id}")
async def get_narrative_metrics_trend(
    book_id: int,
    branch_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    書籍およびブランチごとの指標推移を取得する。
    """
    async with UnitOfWork(AppContainer.db()) as uow:
        # IDOR 防止: 作品の所有権を検証する
        await verify_book_ownership(book_id, current_user, uow)
        metrics = await uow.narrative_metrics.get_trend_metrics(book_id, branch_id)
        return metrics


@router.get("/api/config/planning_options")
async def get_planning_options():
    """
    フロントエンド向けの企画立案用オプション（ジャンル、アーキタイプ、文体、構造テンプレート）を返す。

    旧実装は存在しない定数を import していたため、このエンドポイントは常に
    ImportError で HTTP 500 を返していた。構造テンプレートの供給元は
    STORY_SPINE（`config/story_spine/`）に一本化する。
    """
    from config.archetypes_new import EASY_GENRES, STORY_ARCHETYPES
    from config.story_spine import BEAT_VOCABULARY, CARDS, LENGTHS, MARKETS, PATTERNS
    from config.story_spine.genre_registry import genre_payload
    from src.config import STYLE_DEFINITIONS

    # STYLE_DEFINITIONSから必要な部分のみ抽出
    styles = {
        k: {"name": v.get("name", k), "description": v.get("instruction", "")}
        for k, v in STYLE_DEFINITIONS.items()
    }

    growth_curves = list(
        dict.fromkeys(
            v.get("growth_curve")
            for v in STORY_ARCHETYPES.values()
            if isinstance(v, dict) and "growth_curve" in v
        )
    )

    return {
        # --- 既存キー（フロントが使っているため削除しない） ---
        "easy_genres": EASY_GENRES,
        "story_archetypes": list(STORY_ARCHETYPES.keys()),
        "growth_curves": growth_curves,
        "style_definitions": styles,
        # --- STORY_SPINE（構造テンプレート） ---
        "cards": [{"card_id": k, **v} for k, v in CARDS.items()],
        "lengths": LENGTHS,
        "markets": MARKETS,
        "patterns": PATTERNS,
        "genres": genre_payload(),
        "beat_vocabulary": {
            b.key: {
                "key": b.key,
                "label": b.label,
                "role": b.role,
                "tension": b.tension,
                "artifact": b.artifact,
                "span": list(b.span),
            }
            for b in BEAT_VOCABULARY.values()
        },
    }
