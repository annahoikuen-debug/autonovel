from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.auth import get_current_user
from src.backend.database import get_async_db
from src.backend.database.models import Illustration, User
from src.backend.database.uow import UnitOfWork
from src.backend.security.owner_guard import verify_book_ownership
from src.core.container import AppContainer
from src.dependencies import get_illustration_workflow
from src.models.illustration import (
    IllustrationModel,
    IllustrationRequest,
    IllustrationType,
    SafetyLevel,
)
from src.services.billing.credit_service import CreditService, InsufficientCreditsError

router = APIRouter()


class _ReporterShim:
    """StatusReporter Protocol の軽量実装 (API 用ダミー)。"""

    def __init__(self, id: str):
        self.id = id

    def report(self, message: str, level: str = "info") -> None:
        pass

    def update_progress(
        self, current: int, total: int, message: str = "", sub_message: str = ""
    ) -> None:
        pass

    @property
    def state(self):
        class _S:
            def should_stop(self) -> bool:
                return False

        return _S()


@router.post("/generate")
async def generate_illustration(
    request: dict[str, Any],
    workflow=Depends(get_illustration_workflow),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """単一の挿絵を生成する (5クレジット消費)"""
    try:
        # クレジット消費
        credit_service = CreditService(db)
        await credit_service.deduct_credits(
            user_id=current_user.id,
            amount=5,
            transaction_type="illustration_generation",
            description=f"Generate illustration for book {request.get('book_id')}",
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"クレジット残高が不足しています: {e}",
        )

    try:
        # リクエストのパース
        ill_request = IllustrationRequest(
            book_id=request["book_id"],
            illustration_type=IllustrationType(request["illustration_type"]),
            episode_number=request.get("episode_number"),
            model=IllustrationModel(request.get("model", "auto")),
            safety_level=SafetyLevel.R15_CONTENT
            if request.get("enable_r15")
            else SafetyLevel.BLOCK_SOME,
        )

        # 簡易的なレポート (Protocol なのでダミー化)
        _ = _ReporterShim(id="api_gen")

        # Agentを直接呼んで生成
        res = await workflow.illustration_agent.run(request=ill_request)

        if res["status"] == "error":
            raise HTTPException(status_code=500, detail=res["message"])

        return res["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/yonkoma")
async def generate_yonkoma(
    request: dict[str, Any],
    workflow=Depends(get_illustration_workflow),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """1話分の流れを 6 コマ (デフォルト) で要約した漫画プロンプト+画像を生成する。

    Request:
        {
            "book_id": int,
            "episode_text": str,        # 1話分の本文
            "panels": int = 6,          # 3〜6 (省略時 6)
            "model": str = "auto",      # fast/quality/ultra/auto
            "enable_r15": bool = false,
            "book_context": dict = {}   # title/genre/character_name 等
        }

    Response: IllustrationResult 互換の dict
    """
    yonkoma_enabled = bool(request.get("yonkoma_enabled", True))
    if yonkoma_enabled:
        try:
            credit_service = CreditService(db)
            await credit_service.deduct_credits(
                user_id=current_user.id,
                amount=20,
                transaction_type="illustration_yonkoma",
                description=f"Generate yonkoma for book {request.get('book_id')}",
            )
        except InsufficientCreditsError as e:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"クレジット残高が不足しています: {e}",
            )

    try:
        book_id = int(request["book_id"])
        episode_text = str(request.get("episode_text") or "")
        panels = max(3, min(int(request.get("panels") or 6), 6))
        model = request.get("model", "auto")
        enable_r15 = bool(request.get("enable_r15"))
        book_context = dict(request.get("book_context") or {})

        ill_request = IllustrationRequest(
            book_id=book_id,
            illustration_type=IllustrationType.YONKOMA,
            episode_number=request.get("episode_number"),
            scene_text=episode_text,
            book_context=book_context,
            model=IllustrationModel(model),
            safety_level=(SafetyLevel.R15_CONTENT if enable_r15 else SafetyLevel.BLOCK_SOME),
            panels=panels,
        )

        # オフ設定でも、UI がプレビュー目的で叩く可能性があるため常にプロンプトは返す。
        # 画像生成は settings.yonkoma_enabled=False ならスキップする (呼び出し側で分岐)。
        if not yonkoma_enabled:
            res = await workflow.illustration_agent.generate_prompt_only(request=ill_request)
        else:
            res = await workflow.illustration_agent.generate_episode_yonkoma(
                episode_text=episode_text, request=ill_request, panels=panels
            )
            # 既存 run() の戻り値形式に揃える
            res = {"status": "success", "result": res, "prompt": res.prompt}

        if res.get("status") == "error":
            raise HTTPException(status_code=500, detail=res.get("message"))

        return res["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch")
async def batch_generate_illustrations(
    params: dict[str, Any],
    current_user: User = Depends(get_current_user),
    workflow=Depends(get_illustration_workflow),
):
    """バッチで挿絵を生成する (Huey タスクキューに投入)。

    レスポンスは即座に ``{task_id, status: "queued"}`` を返し、
    進捗・結果は ``GET /api/illustrations/status/{task_id}`` で取得する。
    """
    import uuid

    from src.backend.tasks.illustration_tasks import illustrate_batch_task

    try:
        # 文字列の book_id がそのまま Huey タスクへ流れるとクエリが壊れるため、
        # 所有権検証。以前はここで int 化していなかった。
        book_id = int(params["book_id"])
        settings = params.get("settings", {})
        task_id = f"illust_{uuid.uuid4().hex[:12]}"

        # 生成是有偿的: 他人の book_id を指定してタスクを積ませないよう所有者を確認する。
        await verify_book_ownership(book_id, current_user, AppContainer.db())

        # ワーカー側でも同じ task_id を使う（ずれると status が取れなくなる）
        illustrate_batch_task(book_id=book_id, settings=settings, task_id=task_id)

        return {"task_id": task_id, "status": "queued"}
    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"必須パラメータがありません: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/images/{book_id}/{scene_name}")
async def get_scene_illustration(
    book_id: int,
    scene_name: str,
    current_user: User = Depends(get_current_user),
):
    """シーンに対応する挿絵画像 URL を返す（Studio のプレビュー用）。

    フロントは「まだ生成されていない」状態と「取得に失敗した」状態を区別したいので、
    見つからない場合は 404 ではなく **200 + ``found: false``** を返す。
    （404 にするとフロント側で例外処理が要り、「未生成」と「障害」が混同される）

    Response:
        {"found": true,  "image_url": "https://...", "illustration_id": 12}
        {"found": false, "image_url": null,   "illustration_id": null}

    ``scene_name`` はプロンプトに埋め込まれたシーン名を想定しているため、
    完全一致に処分し、無ければ最も新しい挿絵へフォールバックする。
    """
    async with UnitOfWork(AppContainer.db()) as uow:
        # IDOR 防止: 作品の所有権を必ず検証する
        await verify_book_ownership(book_id, current_user, uow)

        # 1) シーン名がプロンプトに含まれている挿絵を新しい順に探す
        stmt = (
            select(Illustration)
            .where(
                Illustration.book_id == book_id,
                Illustration.image_url != "",
            )
            .order_by(Illustration.id.desc())
        )
        result = await uow.session.execute(stmt)
        candidates = list(result.scalars().all())

    normalized = scene_name.strip()
    # image_url が空（prompt 生成のみ）の行は「画像あり」と見なさない。
    # SQL 側でも絞っているが、二重で保証する。
    usable = [row for row in candidates if (row.image_url or "").strip()]
    matched = next(
        (row for row in usable if normalized and normalized in (row.prompt or "")),
        usable[0] if usable else None,
    )

    if matched is None:
        return {"found": False, "image_url": None, "illustration_id": None}

    return {
        "found": True,
        "image_url": matched.image_url,
        "illustration_id": matched.id,
    }


@router.get("/status/{task_id}")
async def get_illustration_status(
    task_id: str, current_user: User = Depends(get_current_user)
):
    """Huey タスクのステータス・結果を取得する。"""
    from src.backend.database.core import get_db_manager
    from src.backend.database.repository import BookRepository

    db = get_db_manager()
    async with db.get_session() as session:
        repo = BookRepository(session)
        # `get_task` は同期版で、AsyncSession を使うと coroutine が返り
        # `task.status` で AttributeError（=常に 500）になっていた。
        task = await repo.get_task_async(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"task {task_id} not found")
        result = None
        if task.status == "completed" and task.result:
            try:
                import json as _json

                result = _json.loads(task.result)
            except Exception:  # noqa: BLE001
                result = task.result
        return {
            "task_id": task_id,
            "status": task.status,
            "result": result,
        }
