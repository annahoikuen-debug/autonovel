# src/backend/routers/orchestrated.py
"""マルチエージェントオーケストレーション API エンドポイント。

[DEPRECATED in v5.0+]:
本モジュールは旧マルチエージェント生成用レガシーエンドポイントです。
v5.0以降の正規執筆パイプラインには `src.domain.writing` および
`src.backend.routers.easy_mode` を使用してください。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field

from src.backend import database
from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.backend.database.repository import BookRepository
from src.backend.observability.health import metrics
from src.backend.rate_limit import generate_limiter
from src.backend.routers.tasks import _assert_task_ownership
from src.backend.security.owner_guard import verify_book_ownership
from src.backend.tasks.generation_tasks import generate_chapter_orchestrated_task
from src.backend.tasks.huey import huey
from src.agents.event_bus import EventBus, AgentEvent
try:
    from sse_starlette.sse import EventSourceResponse
except ImportError:
    EventSourceResponse = Any  # type: ignore

# prefix は frontend/src/api/orchestratedApi.ts の `BASE = "/orchestrated"` 契約に一致させる。
# prefix を付けないと /generate や /status/{task_id} がルート直下に露出し、
# FE が叩く /orchestrated/* が 404 になる。
router = APIRouter(
    prefix="/orchestrated",
    tags=["orchestrated"],
    # 従来は認証依存が無く、GlobalAuthMiddleware を通過した任意のテナントが
    # 他人のタスク結果閲覧・キャンセル・エ-Agent イベント購読を行えた。
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)

# Agent イベントの correlation_id は `book_<book_id>_branch_<branch_id>_ep_<ep_num>`
# 形式（generation_tasks.py:188）で生成される。branches.py 側は `str(book_id)` を使うため、
# 数値のみのパターンも併せて受け付ける。
_CORRELATION_BOOK_RE = re.compile(r"^book_(\d+)(?:_|$)")


def _book_id_from_correlation(correlation_id: str) -> int | None:
    """correlation_id から作品 ID を抽出する。判定不能な場合は None。"""
    m = _CORRELATION_BOOK_RE.match(correlation_id)
    if m:
        return int(m.group(1))
    if correlation_id.isdigit():
        return int(correlation_id)
    return None


class OrchestratedGenerateRequest(BaseModel):
    """オーケストレーション版生成リクエスト。"""

    book_id: int = Field(default=1, ge=1, description="作品ID")
    branch_id: int = Field(default=1, ge=1, description="ブランチID")
    ep_num: int = Field(default=1, ge=1, description="エピソード番号")
    title: str = Field(..., min_length=1, max_length=200, description="作品タイトル")
    synopsis: str = Field(default="", description="あらすじ")
    target_eps: int = Field(default=10, ge=1, le=100, description="目標総話数")
    concept: str = Field(default="", description="コンセプト")
    genre: str = Field(default="fantasy", description="ジャンル")
    keywords: str = Field(default="", description="キーワード")
    target_word_count: int = Field(default=3000, ge=500, le=10000, description="目標文字数")
    style_tag: str | None = Field(default=None, description="文体タグ")
    llm_config: dict[str, Any] | None = Field(default=None, description="LLM設定")


class OrchestratedGenerateResponse(BaseModel):
    """生成起動レスポンス。"""

    task_id: str
    status: str
    message: str


@router.post("/generate", response_model=OrchestratedGenerateResponse)
async def generate_orchestrated(
    input_data: OrchestratedGenerateRequest,
    request: Request,
    session=Depends(database.get_db),
    current_user: User = Depends(get_current_user),
) -> OrchestratedGenerateResponse:
    """マルチエージェントオーケストレーションによる章生成をキューに投入。"""
    await generate_limiter.check(request)

    # ブックの所有権チェック
    repo = BookRepository(session)
    book = repo.get_book(input_data.book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定された作品が存在しません")
    if current_user.role != "admin" and getattr(book, "user_id", None) is not None:
        if book.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="この作品に対する生成権限がありません")

    try:
        # リクエストを dict に変換
        params: dict[str, Any] = input_data.model_dump()

        # Huey 非同期タスクとして投入
        task_result = generate_chapter_orchestrated_task(params)
        huey_task_id = str(task_result.id)
        params["task_id"] = huey_task_id

        # DB レコードを作成
        repo = BookRepository(session)
        repo.create_task(task_id=huey_task_id, status="running", user_id=current_user.id)

        metrics.increment("orchestrated_tasks_enqueued")
        logger.info("Enqueued orchestrated generation task: task_id=%s", huey_task_id)

        return OrchestratedGenerateResponse(
            task_id=huey_task_id,
            status="pending",
            message=f"オーケストレーション生成タスク ID: {huey_task_id} を投入しました。ステータスを /orchestrated/status/{huey_task_id} で確認してください。",
        )
    except Exception as e:
        logger.exception("Internal orchestrated generation error")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status/{task_id}")
async def get_orchestrated_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """オーケストレーションタスクのステータス取得。"""
    result = huey.result(task_id)

    # IDOR 防止: task_id は連番/推測可能なため、タスク所有者を必ず検証する。
    # `tasks.py` の `_assert_task_ownership` と同じ fail-closed 方針に従う
    # （所有者が記録されていないタスクは管理者のみ参照可）。
    _assert_task_ownership(
        result if isinstance(result, dict) else {}, current_user
    )

    if result is None:
        logger.info("Orchestrated task status polled (pending): task_id=%s", task_id)
        return {"task_id": task_id, "status": "pending"}

    if isinstance(result, dict) and result.get("error"):
        logger.info(
            "Orchestrated task status polled (failed): task_id=%s error=%s",
            task_id,
            result["error"],
        )
        return {"task_id": task_id, "status": "failed", "error": result["error"], "result": result}

    logger.info("Orchestrated task status polled (completed): task_id=%s", task_id)
    return {"task_id": task_id, "status": "completed", "result": result}


@router.delete("/task/{task_id}")
async def cancel_orchestrated_task(
    task_id: str,
    session=Depends(database.get_async_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """オーケストレーションタスクをキャンセル。"""
    # IDOR 防止: 他人のタスクをキャンセルできないようにする。
    # `Task` モデルに user_id 列が無いため、`_assert_task_ownership` は
    # 所有者が不明なら管理者以外を拒否する（fail-closed）。
    repo = BookRepository(session)
    task = await repo.get_task_async(task_id)
    _assert_task_ownership({"user_id": getattr(task, "user_id", None)}, current_user)

    try:
        huey.revoke_by_id(task_id)
    except Exception:
        logger.warning("Failed to revoke huey task_id=%s", task_id)

    await repo.update_task_status_async(task_id, "cancelled")

    return {"task_id": task_id, "status": "cancelled"}


@router.get("/export/{book_id}")
async def export_orchestrated_package(
    book_id: int = Path(ge=1),
    session=Depends(database.get_db),
    current_user: User = Depends(get_current_user),
):
    """オーケストレーション版の納品パッケージ (ZIP) をエクスポート。"""
    import urllib.parse
    from fastapi import Response

    repo = BookRepository(session)
    book = repo.get_book(book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定された作品が存在しません")
    if current_user.role != "admin" and getattr(book, "user_id", None) is not None:
        if book.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="この作品のエクスポート権限がありません")

    logger.info("Orchestrated export requested: book_id=%s", book_id)
    metrics.increment("orchestrated_exports_attempted")
    from src.agents.marketing import MarketingAgent
    from src.services.llm.factory import get_llm_adapter

    # MarketingAgent で ZIP 生成
    llm_adapter = get_llm_adapter()
    agent = MarketingAgent(repo=repo, llm=llm_adapter)
    zip_bytes, zip_filename = await agent.create_export_package(book_id)

    encoded_filename = urllib.parse.quote(zip_filename)
    ascii_filename = zip_filename.encode("ascii", "ignore").decode("ascii") or "export.zip"

    logger.info(
        "Orchestrated export succeeded: book_id=%s bytes=%d filename=%s",
        book_id,
        len(zip_bytes),
        zip_filename,
    )
    metrics.increment("orchestrated_exports_succeeded")

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"
            ),
            "Cache-Control": "no-store",
        },
    )


@router.get("/events/{correlation_id}")
async def orchestrated_events(
    correlation_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> EventSourceResponse:
    """オーケストレーション中のAgentEventをSSEでリアルタイム配信。

    IDOR 防止: correlation_id は単なる識別子（`book_<id>_branch_<id>_ep_<n>`）で、
    他人の生成イベントを購読できてしまう。作品 ID を解決して所有者を検証する。
    """
    book_id = _book_id_from_correlation(correlation_id)
    if book_id is None:
        # 作品スコープに紐づけられない correlation_id は管理者に限定する (fail-closed)
        if getattr(current_user, "role", None) != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="このイベントストリームは作品に紐づかないため管理者権限が必要です",
            )
    else:
        await verify_book_ownership(book_id, current_user)

    use_redis = os.environ.get("USE_REDIS_EVENTS", "false").lower() == "true"
    event_bus = EventBus(use_redis=use_redis)
    if use_redis:
        await event_bus.start_redis()

    queue: asyncio.Queue = asyncio.Queue()

    def handler(event: AgentEvent) -> None:
        queue.put_nowait(event)

    event_bus.subscribe(correlation_id, lambda e: asyncio.create_task(asyncio.to_thread(handler, e)))

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {"event": "agent_event", "data": json.dumps(event.__dict__, ensure_ascii=False)}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": "{}"}
        finally:
            event_bus._subs.get(correlation_id, []).remove(handler)
            if use_redis:
                await event_bus.stop_redis()

    return EventSourceResponse(event_generator())
