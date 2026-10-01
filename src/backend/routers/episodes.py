import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.backend.auth import get_current_user, require_valid_api_key
from src.backend.database.models import Book, Branch, User
from src.backend.database.uow import UnitOfWork
from src.backend.security.owner_guard import verify_book_ownership
from src.backend.task_helpers import create_task as _create_task
from src.core.container import AppContainer
from src.core.observability import TraceContext
from src.models.api_schemas import (
    ChapterImportRequest,
    EpisodeGenerateCandidatesRequest,
    EpisodeGenerateRequest,
    RetryFailedRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/episodes",
    tags=["episodes"],
    dependencies=[Depends(get_current_user)],
)


class ChapterUpsertRequest(BaseModel):
    """1 話を保存/更新するリクエスト。

    ``ep_num`` はパスで受け取るため、通常は body に入れない。
    """

    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=2_000_000)
    summary: str = Field(default="", max_length=4000)
    branch_id: int = Field(default=1, ge=1)


class ChapterUpsertResponse(BaseModel):
    book_id: int
    branch_id: int
    ep_num: int
    saved: bool
    created: bool = False


class ChapterDeleteResponse(BaseModel):
    book_id: int
    branch_id: int
    ep_num: int
    deleted: bool


@router.put("/chapters/{book_id}/{ep_num}", response_model=ChapterUpsertResponse)
async def upsert_chapter(
    book_id: int,
    ep_num: int,
    payload: ChapterUpsertRequest,
    current_user: User = Depends(get_current_user),
):
    """1 話を Upsert する（無ければ作成、あれば更新）。

    Studio の章操作（追加/編集/並び替え）と Wizard の執筆保存の両方が
    ここを使うことで、「チャ保存」の API を増やさずに済むため。

    - IDOR 防止として所有権を検証する
    - ``(book_id, branch_id, ep_num)`` の UNIQUE 制約に従い、既存行があれば更新する
    """
    if ep_num < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ep_num は 1 以上にしてください",
        )

    async with UnitOfWork(AppContainer.db()) as uow:
        await verify_book_ownership(book_id, current_user, uow)
        await _verify_branch_belongs_to_book(uow, book_id, payload.branch_id)

        # 生成済みメタデータ（killer_phrase / ai_insight / world_state /
        # trinity_review_log / created_at）は渡さない。
        # 渡すと upsert が既存値を上書きして、消してしまうため。
        updated = await uow.chapters.create_chapter(
            book_id=book_id,
            ep_num=ep_num,
            title=payload.title or f"第{ep_num}話",
            content=payload.content,
            summary=payload.summary,
            branch_id=payload.branch_id,
        )

    return {
        "book_id": book_id,
        "branch_id": payload.branch_id,
        "ep_num": ep_num,
        "saved": True,
        "created": not updated,
    }


async def _verify_branch_belongs_to_book(uow: UnitOfWork, book_id: int, branch_id: int) -> None:
    """``branch_id`` が検証済み ``book_id`` に属するかを確認する。

    ``branch_id`` は 1 が全作品の既定値なので、「request が本人の作品である」
    だけでは不十分。他人のブランチ ID を推測して渡されても、他作品の行には
    一切触れないことを保証する。
    """
    if branch_id == 1:
        # 1 は全作品の既定ブランチ。books.current_branch_id が別ブランチを指している
        # なら、その作品で 1 を使うことは許さない。
        book = await uow.books.get_book(book_id)
        current = getattr(book, "current_branch_id", None) if book else None
        if current is not None and current != 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="指定ブランチはこの作品に属していません",
            )
        return

    owner = await uow.session.scalar(
        select(Book.id).where(Branch.book_id == book_id).where(Branch.id == branch_id)
    )
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="指定ブランチはこの作品に属していません",
        )


@router.delete("/chapters/{book_id}/{ep_num}", response_model=ChapterDeleteResponse)
async def delete_chapter(
    book_id: int,
    ep_num: int,
    branch_id: int = 1,
    current_user: User = Depends(get_current_user),
):
    """1 話を削除する（Studio の章削除用）。"""
    if ep_num < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ep_num は 1 以上にしてください",
        )

    async with UnitOfWork(AppContainer.db()) as uow:
        await verify_book_ownership(book_id, current_user, uow)
        await _verify_branch_belongs_to_book(uow, book_id, branch_id)
        deleted = await uow.chapters.delete_chapter(book_id, ep_num, branch_id=branch_id)

    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された話が見つかりません",
        )

    return {"book_id": book_id, "branch_id": branch_id, "ep_num": ep_num, "deleted": True}


async def _cancel_prefetch_for_book(book_id: int | None) -> int:
    """書籍単位のプリフェッチをすべて取り消す（PLAN_W6 Step 10）。

    リトライは「已完成分」を破棄して書き直すため，その之前に出ていた投機プリフェッチは
    すべて無駄になる。レジストリの実キーは `"{book_id}_{ep}"` なので、
    `cancel_prefix` のスコープ一致でまとめて殺す。
    プリフェッチ取り消しが失敗しても API は落とさない（ログのみ）。
    """
    if book_id is None:
        return 0
    try:
        from src.services.rag_prefetch_service import RagPrefetchService

        svc = RagPrefetchService()
        cancelled = await svc._registry.cancel_prefix(f"{book_id}")
        if cancelled:
            logger.info("[W6] cancelled %d prefetch task(s) for book %s", cancelled, book_id)
        return cancelled
    except Exception as e:
        logger.warning("[W6] failed to cancel prefetch for book %s: %s", book_id, e)
        return 0


@router.get("/chapters/{book_id}")
async def get_chapters(book_id: int, current_user: User = Depends(get_current_user)):
    async with UnitOfWork(AppContainer.db()) as uow:
        await verify_book_ownership(book_id, current_user, uow)
        chapters = await uow.chapters.get_all_non_anchor_chapters(book_id)
    return [
        {
            "ep_num": c.ep_num,
            "title": c.title,
            "content": c.content,
            "summary": c.summary,
            "created_at": c.created_at,
        }
        for c in chapters
    ]


def generate_task_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@router.post("/generate")
async def generate_episodes(
    req: EpisodeGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    await verify_book_ownership(req.book_id, current_user, AppContainer.db())
    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("write")
    await _create_task(
        task_id,
        "執筆タスクを開始中...",
        total_steps=req.write_to - req.write_from + 1,
        user_id=getattr(current_user, "id", None),
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="episode_writing_workflow",
        kwargs={
            "book_id": req.book_id,
            "write_from": req.write_from,
            "write_to": req.write_to,
            "passion": req.passion,
            "word_count": req.word_count,
            "do_refine": req.do_refine,
            "env_state": req.env_state,
            "pipeline_mode": req.pipeline_mode,
            "mode": "final",
        },
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/generate_candidates")
async def generate_episodes_candidates(
    req: EpisodeGenerateCandidatesRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    await verify_book_ownership(req.book_id, current_user, AppContainer.db())
    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("write_candidates")
    await _create_task(
        task_id,
        "本文候補案を生成中...",
        total_steps=req.write_to - req.write_from + 1,
        user_id=getattr(current_user, "id", None),
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="episode_writing_workflow",
        kwargs={
            "book_id": req.book_id,
            "write_from": req.write_from,
            "write_to": req.write_to,
            "passion": req.passion,
            "word_count": req.word_count,
            "do_refine": req.do_refine,
            "env_state": req.env_state,
            "pipeline_mode": req.pipeline_mode,
            "mode": "candidates",
        },
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/retry_failed")
async def retry_failed_episodes(
    req: RetryFailedRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    await verify_book_ownership(req.book_id, current_user, AppContainer.db())

    # PLAN_W6 Step 10: リトライ前に、進行中の投機プリフェッチをすべて取り消す。
    await _cancel_prefetch_for_book(req.book_id)

    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("retry_failed")
    await _create_task(
        task_id,
        "失敗エピソードの修復を開始中...",
        total_steps=1,
        user_id=getattr(current_user, "id", None),
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="retry_failed_episodes_workflow",
        kwargs={"book_id": req.book_id, "passion": req.passion, "word_count": req.word_count},
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/chapters/import")
async def import_chapter(
    req: ChapterImportRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    await verify_book_ownership(req.book_id, current_user, AppContainer.db())
    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("import")
    await _create_task(
        task_id,
        "手書き原稿のインポートと研磨を開始中...",
        total_steps=1,
        user_id=getattr(current_user, "id", None),
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict={},
        method_name="chapter_import_workflow",
        kwargs={
            "book_id": req.book_id,
            "ep_num": req.ep_num,
            "import_text": req.import_text,
            "do_refine": req.do_refine,
        },
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}
