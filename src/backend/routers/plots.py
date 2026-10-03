import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.backend.auth import get_current_user, require_valid_api_key
from src.backend.database.models import User
from src.backend.database.uow import UnitOfWork
from src.backend.engine_helpers import get_engine as resolve_engine
from src.backend.security.owner_guard import verify_book_ownership
from src.backend.task_helpers import create_task as _create_task
from src.core.container import AppContainer
from src.core.exceptions import AppError
from src.core.observability import TraceContext
from src.core.llm_gateway import LLMGateway
from src.services.llm.prompts import build_spine_summary
from src.services.spine_resolver import resolve_spine
from src.models.api_schemas import (
    AuditPlanRequest,
    PlanGenerationRequest,
    PlotExpandCandidatesRequest,
    PlotExpandRequest,
    PlotRebuildRequest,
    ReversePlotGenerateRequest,
    ExpandBeatsRequest,
    BeatItemSchema,
)

logger = logging.getLogger(__name__)

# 商業ビート生成用システム指示
PLANNER_SYSTEM_INSTRUCTION = """あなたは商業Web小説の構成プロデューサーです。
企画パラメータに基づき、読者を引き込む12ステップのビートシート（五感フォーカス・クリフハンガー種別付き）を生成してください。
Save the Cat!のビートシート構成に準拠し、日本のWeb小説市場でヒットする構成を意識してください。"""

router = APIRouter(
    prefix="/api/plots",
    tags=["plots"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{book_id}")
async def get_plots(book_id: int, current_user: User = Depends(get_current_user)):
    async with UnitOfWork(AppContainer.db()) as uow:
        await verify_book_ownership(book_id, current_user, uow)
        # 第1位置引数は branch_id カラムに効くため、本Branchesの既定ブランチ 1 を明示し
        # book_id で作品を絞る（既定ブランチは全作品で 1 が共有される）。
        plots = await uow.plots.get_all_plots(1, branch_id=1, book_id=book_id)
    return [
        {
            "ep_num": p.ep_num,
            "title": p.title,
            "summary": p.summary,
            "detailed_blueprint": p.detailed_blueprint,
            "tension": p.tension,
            "is_catharsis": p.is_catharsis,
            "status": p.status,
        }
        for p in plots
    ]


def generate_task_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@router.post("/plan_generation")
async def plan_generation(
    req: PlanGenerationRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("plan_gen")
    await _create_task(
        task_id, "企画作成を開始中...", total_steps=1, user_id=getattr(current_user, "id", None)
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="plan_generation_workflow",
        kwargs={"params": req.params},
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/expand")
async def expand_plots(
    req: PlotExpandRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    await verify_book_ownership(req.book_id, current_user, AppContainer.db())
    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("plot_expand")
    await _create_task(
        task_id,
        "プロット作成を開始中...",
        total_steps=req.gen_to - req.gen_from + 1,
        user_id=getattr(current_user, "id", None),
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="plot_expansion_workflow",
        kwargs={
            "book_id": req.book_id,
            "gen_from": req.gen_from,
            "gen_to": req.gen_to,
            "mode": "final",
        },
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/expand_candidates")
async def expand_plots_candidates(
    req: PlotExpandCandidatesRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    await verify_book_ownership(req.book_id, current_user, AppContainer.db())
    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("plot_candidates")
    await _create_task(
        task_id,
        "プロット候補案を生成中...",
        total_steps=req.gen_to - req.gen_from + 1,
        user_id=getattr(current_user, "id", None),
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="plot_expansion_workflow",
        kwargs={
            "book_id": req.book_id,
            "gen_from": req.gen_from,
            "gen_to": req.gen_to,
            "mode": "candidates",
        },
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/rebuild")
async def rebuild_plots(
    req: PlotRebuildRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    import json
    import time

    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("plot_rebuild")
    db = AppContainer.db()
    initial_state = {
        "is_running": True,
        "current_step": 0,
        "total_steps": 1,
        "message": "プロット再構築を開始中...",
        "sub_message": "キューの待機中",
        "streaming_text": "",
        "logs": [f"[{time.strftime('%H:%M:%S')}] 🚀 プロット再構築タスクを登録しました。"],
        "error": None,
        "result_data": None,
        "token_usage": {"prompt": 0, "completion": 0, "calls": 0},
        "start_time": time.time(),
        "last_updated": time.time(),
    }
    await db.save_internal_state(
        f"task_status:{task_id}", json.dumps(initial_state), time.strftime("%Y-%m-%d %H:%M:%S")
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="plot_rebuild_workflow",
        kwargs={"params": req.params},
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/audit")
async def audit_plan(
    req: AuditPlanRequest,
    current_user: User = Depends(get_current_user),
):
    if req.api_key:
        require_valid_api_key(req.api_key)
    engine = resolve_engine(req.api_key)
    res = await engine.planner.audit_producer_plan(
        req.genre,
        req.keywords,
        req.trend_memo,
        sanctuary=req.sanctuary,
        originality_score=req.originality_score,
        platform=req.platform,
    )
    if not res:
        raise AppError("Audit failed")
    return {
        "refined_keywords": res.refined_keywords,
        "refined_concept": res.refined_concept,
        "refined_mc_suggestion": res.refined_mc_suggestion,
        "recommended_tropes": res.recommended_tropes,
        "candidates": [c.model_dump() for c in res.candidates],
    }


@router.post("/reverse-generate")
async def reverse_generate_plot(
    req: ReversePlotGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """逆算プロットビルダーからの回答を受け、プロット構造を生成"""
    if req.api_key:
        require_valid_api_key(req.api_key)
    from src.backend.tasks import execute_service_workflow

    task_id = generate_task_id("reverse_plot")
    await _create_task(
        task_id,
        "逆算プロット構造を生成中...",
        total_steps=3,
        user_id=getattr(current_user, "id", None),
    )
    execute_service_workflow(
        task_id=task_id,
        api_key=req.api_key,
        config_dict=req.config,
        method_name="reverse_plot_generation_workflow",
        kwargs={
            "answers": req.answers,
            "target_episodes": req.target_episodes,
            "genre": req.genre,
        },
        trace_id=TraceContext.get_trace_id(),
    )
    return {"task_id": task_id}


@router.post("/wizard-save")
async def wizard_save(
    req: ExpandBeatsRequest,
    current_user: User = Depends(get_current_user),
):
    """ウィザードで作成した企画とビートシートをDBに保存する"""
    if req.api_key:
        require_valid_api_key(req.api_key)

    from src.backend.database.models import Book

    async with UnitOfWork(AppContainer.db()) as uow:
        # 新規Bookを作成
        book = Book(
            user_id=getattr(current_user, "id", None),
            title=req.title,
            genre=req.genre,
            concept="",
            synopsis=req.synopsis,
            target_eps=req.target_chapters,
        )
        uow.session.add(book)
        await uow.session.flush()
        book_id = book.id

        # ビートシートをPlotとして保存
        beats = req.beats if req.beats else []
        from src.backend.database.models_foreshadowing import ForeshadowingModel
        from src.services.foreshadowing.planner import plan_foreshadowing

        # v5.3: 回収予定話数の決定に作品全体の話数を使う
        total_eps = len(beats) or req.target_chapters or None

        for i, beat in enumerate(beats, start=1):
            ep_num = beat.episode if beat.episode else i
            await uow.plots.create_or_replace_plot(
                book_id=book_id,
                ep_num=ep_num,
                thought_process="wizard_creation_funnel",
                title=beat.title,
                summary=beat.outline,
                detailed_blueprint=beat.foreshadowing_notes or "",
                next_hook=beat.cliffhanger_type or "New Crisis",
                tension=50,
                status="open",
            )

            # 伏線メモが存在する場合は伏線ステートマシンテーブル（foreshadowings）へ登録
            if beat.foreshadowing_notes and beat.foreshadowing_notes.strip():
                # v5.3: scope / target_episode をビートシート基準で決定する
                # （旧: "ep_num <= 5 → short_term" ＋ target_episode=NULL）
                plan = plan_foreshadowing(
                    planted_episode=ep_num,
                    total_episodes=total_eps or ep_num,
                )
                fs = ForeshadowingModel(
                    book_id=book_id,
                    title=f"第{ep_num}話: {beat.title or '伏線'}",
                    description=beat.foreshadowing_notes.strip(),
                    planted_episode=ep_num,
                    target_episode=plan.target_episode,
                    status="planted",
                    scope=plan.scope.value,
                )
                uow.session.add(fs)

    return {"book_id": book_id, "branch_id": 1, "success": True}



@router.post("/expand-beats", response_model=list[BeatItemSchema])
async def expand_commercial_beats(
    req: ExpandBeatsRequest,
    current_user: User = Depends(get_current_user),
):
    """企画パラメータから構造テンプレートに基づくビートシートを生成"""
    if req.api_key:
        require_valid_api_key(req.api_key)

    # STORY_SPINE: 話数と構造から各話の役割を解決する（LLM を呼ばない）。
    # 12ステップ固定は 1話短編や 300話長編で成立しないため廃止した。
    spine = resolve_spine(
        req.pattern_key or "exile_rise",
        req.length_key or "web_volume",
        req.market_key or "web",
        req.target_chapters,
    )
    spine_summary = build_spine_summary(spine)
    beat_plan = "\n".join(
        f"{i + 1}. 第{b.ep_start}-{b.ep_end}話 / {b.label}: {b.duty}"
        for i, b in enumerate(spine.beats)
    )

    llm = LLMGateway()
    prompt = f"""【作品タイトル】{req.title}
【ジャンル】{req.genre}
【あらすじ】{req.synopsis}
【目標話数】{req.target_chapters}
【チート度 (1-5)】{req.cheat_scale}
【成長曲線】{req.growth_curve}
【システム支援度 (0-100)】{req.system_assist}
【代償・リスク過酷度 (1-5)】{req.cost_severity}
【構造テンプレート】{spine.pattern} / {spine.length} / {spine.market}
【構造の割当】{spine_summary}

上記の企画パラメータに基づき、**【構造の割当】で指定された各話の役割这一幕**を
ビートシート（五感フォーカス・クリフハンガー種別付き）として生成してください。
割当で指定された役割を省略・順序変更してはいけません。各ステップは以下の構造で出力してください：

```json
[
  {{
    "episode": 1,
    "title": "エピソードタイトル",
    "outline": "このエピソードで起こる出来事の詳細（3-5行）",
    "cliffhanger_type": "New Crisis | Shocking Truth | Quiet Foreshadowing",
    "sensory_focus": ["visual", "auditory", "olfactory", "tactile", "gustatory", "metaphor"],
    "foreshadowing_notes": "伏線メモ（あれば）"
  }},
  ...
]
```

割当の指示（{len(spine.beats)} 項目）:
{beat_plan}

クリフハンガー種別の使い分け:
- New Crisis: 新たな危機・敵の出現・予期せぬトラブル（アクション・サスペンス向き）
- Shocking Truth: 衝撃の真実・正体発覚・裏切り（ミステリー・どんでん返し向き）
- Quiet Foreshadowing: 静かな伏線・感情の変化・小さな違和感（心情・日常・伏線回収向き）

五感フォーカスは各話2-3種類をバランスよく配分してください。"""

    degraded_reason: str | None = None

    try:
        res = await llm.generate_text(
            purpose_or_request="planning",
            prompt=prompt,
            system_instruction=PLANNER_SYSTEM_INSTRUCTION,
            temp=0.7,
        )
        raw_text = getattr(res, "story_content", "") or getattr(res, "content", "") or ""
        import json

        try:
            cleaned = str(raw_text).strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            beats_data = json.loads(cleaned)
            if not beats_data:
                degraded_reason = "LLM が空の beats を返した"
            else:
                # 12件への切り詰めは廃止。割当で決まった beat 数だけ受け付ける。
                return beats_data[: len(spine.beats)]
        except Exception as e:
            # JSON パースエラーは「生成失敗」ではなく「整形失敗」なので縮退してよい。
            # ただし黙って消すと原因が追えなくなるため、必ずログに残す。
            logger.warning("[plots] beat JSON の解析に失敗しました: %s", e, exc_info=True)
            degraded_reason = f"beat JSON の解析に失敗: {e}"
    except Exception as e:
        # LLM 呼び出しの失敗（認証エラー・レート制限・プロバイダ障害・タイムアウト）は
        # 縮退の根拠にならない。ここで握り潰して 200 を返すと、
        # 「モデルが出力した」と「API キーが無効」でクライアントが区別できなくなる。
        logger.error("[plots] beat 生成の LLM 呼び出しに失敗しました: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"beat 生成に失敗しました: {e}",
        ) from e

    logger.warning("[plots] 縮退 beat を返します: %s", degraded_reason)

    # フォールバック: 12ステップ固定ではなく、解決済みの Spine から生成する。
    # 1話短編でも「発端 → 中点反転 → クライマックス」が必ず残る。
    _CLIFFHANGER_BY_ROLE = {
        "hook": "New Crisis",
        "engine": "Quiet Foreshadowing",
        "reversal": "Shocking Truth",
        "climax": "Shocking Truth",
        "close": "Quiet Foreshadowing",
    }
    _SENSORY_BY_ARTIFACT = {
        "scene": ["visual", "auditory"],
        "reversal": ["olfactory", "metaphor"],
        "reveal": ["tactile", "auditory"],
        "hook": ["visual", "metaphor"],
    }
    default_beats = [
        {
            "episode": b.ep_start,
            "title": b.label,
            "outline": b.duty,
            "cliffhanger_type": _CLIFFHANGER_BY_ROLE.get(b.role, "Quiet Foreshadowing"),
            "sensory_focus": _SENSORY_BY_ARTIFACT.get(b.artifact, ["visual"]),
            "foreshadowing_notes": f"{b.ep_start}-{b.ep_end}話 / 目標テンション {b.tension:.2f}",
        }
        for b in spine.beats
    ]
    return default_beats
