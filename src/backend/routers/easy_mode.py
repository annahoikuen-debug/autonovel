import logging
import secrets
import time
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi import status as http_status
from pydantic import ValidationError

from src.backend import database
from src.backend.auth import get_current_user, oauth2_scheme, require_api_key
from src.backend.config import settings
from src.backend.database import get_async_db
from src.backend.database.core import get_db_manager
from src.backend.database.repository import BookRepository
from src.backend.observability.health import metrics
from src.backend.rate_limit import generate_limiter
from src.backend.security.owner_guard import verify_book_ownership
from src.domain.entities.easy_mode import EasyModeInput, GenerationResponse
from src.services.digest_service import process_chapter
from src.services.graph_pipeline import graph_pipeline_service
from src.services.llm.factory import get_llm_adapter
from src.services.llm.prompts import (
    NOVEL_SYSTEM_PROMPT,
    NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE,
    SUGGESTIONS_PROMPT_TEMPLATE,
)
from src.services.marketing import MarketingAgent
from src.services.rag_service import rag_service
from src.services.compression.compressor import FourLayerCompressor
from src.services.compression.models import CompressionConfig

router = APIRouter()
logger = logging.getLogger(__name__)


# UI 上のジャンル文字列 → preset key マッピングは
# `config.story_spine.genre_registry.GENRE_REGISTRY` に一本化した。
# 旧実装は日本語キーワードの部分一致だけで、EasyMode が送る `fan` / `sf` /
# `romance` / `mystery` / `horror` / `other` に1つも一致せず、必ず None を返していた
# （スタイルプリセットが1つも効かない状態で EasyMode が走っていた）。
# 旧11キーワードの優先順位は `GENRE_REGISTRY.LEGACY_KEYWORD_PRIORITY` に移設済み。
from config.story_spine import genre_registry as _genre_registry

# 旧11キーワードの優先順位はレジストリ側に移設済み。互換のため名前を維持する。
GENRE_TO_PRESET: list[tuple[str, str]] = list(_genre_registry.LEGACY_KEYWORD_PRIORITY)


def resolve_genre_to_preset(genre: str) -> str | None:
    """UI ジャンル文字列から preset key を解決する（GENRE_REGISTRY に委譲）。"""
    from config.story_spine.genre_registry import resolve_preset_key

    return resolve_preset_key(genre)


def resolve_pattern_key(genre: Any, explicit: str | None = None) -> str:
    """ジャンルから STORY_SPINE パターンキーを解く。未知は exile_rise。"""
    if explicit:
        return explicit
    from config.story_spine import PATTERNS
    from config.story_spine.genre_registry import resolve_genre

    entry = resolve_genre(genre if isinstance(genre, str) else None)
    p = (entry or {}).get("pattern")
    if p and p in PATTERNS:
        return p
    logger.warning("ジャンル %r に pattern 未定義のため exile_rise を使用", genre)
    return "exile_rise"


async def execute_generation(payload: dict[str, Any]) -> dict[str, Any]:
    """LLM アダプタを利用して非同期に小説本文と次話提案を生成する (GraphRAG 統合済み)。"""
    start_time = time.time()
    current_chapter = payload.get("current_chapter", "")
    chapter_history = payload.get("chapter_history", [])
    character = payload.get("character", {})
    chapter_id = payload.get("chapter_id", 1)

    char_name = character.get("name", "主人公")
    genre = character.get("genre", "ハイファンタジー (R15)")
    personality = character.get("personality", "正義感が強い")
    ability = character.get("ability", "剣術・魔導")
    history_context = "\n".join(chapter_history[:-1]) if len(chapter_history) > 1 else "なし"

    # GraphRAG コンテキストの取得
    # ※ book_id を渡さないとコンテキストキャッシュが読み書きされない
    #   （書籍をまたいだキャッシュ汚染を防ぐため、キーには必ず book_id を含める）
    book_id = payload.get("book_id")
    db = get_db_manager()
    async with db.get_session() as session:
        rag_context = await rag_service.build_rag_context(
            session=session,
            book_id=book_id,
            current_prompt=current_chapter,
            character_name=char_name,
        )
        graph_context = rag_context.graph_context
        vector_context = rag_context.vector_context

    # 文体（Style DNA）の解決とプロンプト注入
    from src.models.style_profile import StyleProfile
    from src.presets.loader import load_preset
    from src.services.cadence_reformatter import cadence_reformatter

    style_override = payload.get("style_override")
    style_id = character.get("style_id")

    style_profile: StyleProfile | None = None
    if isinstance(style_override, dict) and style_override:
        try:
            style_profile = StyleProfile(**style_override)
        except Exception as e:
            logger.warning("Failed to parse style_override: %s", e)

    if style_profile is None and style_id:
        try:
            preset_dict = load_preset(style_id)
            style_data = preset_dict.get("style", {})
            if isinstance(style_data, dict) and style_data:
                style_profile = StyleProfile(
                    id=style_id,
                    name=f"{style_id}調",
                    genre_hint=style_id,
                    **{k: v for k, v in style_data.items() if k in StyleProfile.model_fields},
                )
        except Exception:
            pass

    if style_profile is None:
        # ジャンルから preset を解決 (マッピング辞書 GENRE_TO_PRESET を参照)
        genre_key = resolve_genre_to_preset(genre)
        if genre_key:
            try:
                preset_dict = load_preset(genre_key)
                style_data = preset_dict.get("style", {})
                if isinstance(style_data, dict) and style_data:
                    style_profile = StyleProfile(
                        id=genre_key,
                        name=f"{genre_key}標準調",
                        genre_hint=genre_key,
                        **{k: v for k, v in style_data.items() if k in StyleProfile.model_fields},
                    )
            except Exception:
                pass
        if style_profile is None:
            logger.warning("Unknown genre, using empty StyleProfile: %s", genre)
            style_profile = StyleProfile(name=f"{genre}標準文体", genre_hint=genre)

    style_bias_section = style_profile.to_prompt_instruction() if style_profile else ""

    content_length_limit = int(payload.get("content_length_limit") or 2000)
    target_episodes = int(payload.get("target_episodes") or 1)
    llm_config = payload.get("llm_config") or {}

    # STORY_SPINE (B8): 構造指示の段階的注入（既定 spine_quality="off" 時は完全空文字でバイト同一性を保証）
    pattern_key = payload.get("pattern_key") or ""
    length_key = payload.get("length_key") or ""
    market_key = payload.get("market_key") or ""
    spine_quality = payload.get("spine_quality") or None

    spine_section = ""
    try:
        from config.story_spine import resolve_spine
        from src.services.llm.prompts import build_spine_section

        pattern_key = resolve_pattern_key(genre, explicit=pattern_key)

        spine = resolve_spine(
            pattern_key=pattern_key,
            length_key=length_key or "web_volume",
            market_key=market_key or "web",
            total_eps=target_episodes,
        )
        built = build_spine_section(spine, quality=spine_quality, ep_num=chapter_id)
        if built:
            spine_section = f"\n{built}"
    except Exception as exc:
        logger.warning("Spine resolution in easy_mode skipped: %s", exc)
        spine_section = ""

    # GraphRAG を反映したユーザープロンプトの構築
    user_prompt = NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(
        genre=genre,
        char_name=char_name,
        char_personality=personality,
        char_ability=ability,
        style_bias_section=style_bias_section,
        graph_context=graph_context,
        vector_context=vector_context,
        history_context=history_context,
        current_chapter=current_chapter,
        spine_section=spine_section,
    )
    if content_length_limit:
        user_prompt += f"\n\n【執筆指示】1話あたりの目標文字数は約{content_length_limit}文字（目安: {max(500, content_length_limit - 300)}〜{content_length_limit + 300}文字）で執筆してください。"

    from src.llm.model_router import resolve_model_for_purpose

    writing_model = resolve_model_for_purpose("writing", llm_config)
    adapter = get_llm_adapter(
        provider=llm_config.get("provider"),
        api_key=llm_config.get("api_key"),
        model_name=writing_model,
        base_url=llm_config.get("base_url"),
    )
    max_tokens = max(500, min(8000, int(content_length_limit * 1.5)))
    raw_generated_text = await adapter.generate_text(
        prompt=user_prompt,
        system_prompt=NOVEL_SYSTEM_PROMPT,
        max_tokens=max_tokens,
    )

    # ケイデンス・音律ポストプロセッサ（文末連続の自動排除・スマホ改行最適化）
    generated_text, cadence_stats = cadence_reformatter.reformat_novel_text(raw_generated_text)
    logger.info(
        "Cadence reformatted: %d repeated endings fixed across %d sentences (avg len: %.1f)",
        cadence_stats.repeated_endings_fixed,
        cadence_stats.total_sentences,
        cadence_stats.avg_sentence_length,
    )

    # 生成完了後、バックグラウンド/同期でナレッジグラフとベクトルを更新
    db = get_db_manager()
    async with db.get_session() as session:
        try:
            graph_pipeline_service.process_chapter_knowledge(
                session=session,
                chapter_id=chapter_id,
                chapter_text=generated_text,
            )
        except Exception as e:
            logger.warning("Failed to process chapter knowledge in background: %s", e)

    # 次話展開提案の生成 (planningモデルを使用)
    planning_model = resolve_model_for_purpose("planning", llm_config)
    planning_adapter = (
        adapter
        if planning_model == writing_model
        else get_llm_adapter(
            provider=llm_config.get("provider"),
            api_key=llm_config.get("api_key"),
            model_name=planning_model,
            base_url=llm_config.get("base_url"),
        )
    )
    suggestions_prompt = SUGGESTIONS_PROMPT_TEMPLATE.format(chapter_text=generated_text[:1000])
    try:
        suggestions_raw = await planning_adapter.generate_text(
            prompt=suggestions_prompt,
            max_tokens=300,
        )
        suggestions = [
            line.lstrip("- ").strip()
            for line in suggestions_raw.strip().split("\n")
            if line.strip()
        ][:3]

    except Exception:
        logger.warning("Failed to generate suggestions, using defaults", exc_info=True)
        suggestions = [
            "新たな仲間との出会いと衝突",
            "古代遺跡に隠された真実の解明",
            "強敵の急襲と覚醒する未知の力",
        ]

    elapsed_ms = int((time.time() - start_time) * 1000)
    return {
        "output": generated_text,
        "suggestions": suggestions,
        "completion_time_ms": elapsed_ms,
    }


# 後方互換性エイリアス
generate_with_llm = execute_generation


async def _ensure_dev_user_row(db: Any) -> None:
    """``AUTH_DISABLED`` 時に開発用モックユーザー (id=1) の行を確保する。

    ``tasks.user_id`` は ``users.id`` への外部キーのため、行が無い状態で
    ``user_id=1`` を書くと投入が IntegrityError で 500 になる。
    ``init_db`` は作品を seed するがユーザーは作らないため、開発/テストでは
    ここで補う。``AUTH_DISABLED`` のときしか通らない経路であり、
    値は開発用の固定値のみ（認証は既に無効になっている）。
    """
    from src.backend.auth import _get_dev_mock_user
    from src.backend.database.models import User

    dev = _get_dev_mock_user()
    try:
        if await db.get(User, dev.id) is not None:
            return
        db.add(
            User(
                id=dev.id,
                email=dev.email,
                # パスワードは使わないが NOT NULL。ランダム値を置いて
                # 意図せずログイン可能にならないようにする。
                hashed_password=secrets.token_hex(32),
                display_name=dev.display_name,
                role=dev.role,
                status=dev.status,
                plan_tier=dev.plan_tier,
                credits=dev.credits,
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 - seed 失敗で投入を落とさない
        await db.rollback()
        logger.warning("Failed to seed AUTH_DISABLED dev user row", exc_info=True)


async def get_current_user_or_api_key_owner(
    token: str = Depends(oauth2_scheme),
    db=Depends(get_async_db),
) -> Any:
    """easy-mode のタスク所有者を解決する FastAPI 依存。

    easy-mode はフロントエンドが API キー（``Authorization`` ヘッダー）で叩くため、
    ``require_api_key`` を認証手段として採用している。一方で投入される Huey タスクは
    ``/status/{task_id}`` から参照されるため、所有者を必ず特定できる必要がある
    （``Task.user_id`` が NULL のままだと ``_assert_task_ownership`` が
    *自分の* タスクまで拒否する = エンドポイント相互運用性の破綻）。

    そのためここでもう 1 本、ユーザーを解決する:
    1. ``AUTH_DISABLED``（開発/テスト）なら開発用モックユーザーを返す。
    2. JWT (Bearer) が引ければそのユーザーを返す。
    3. どちらでも所有者を特定できない場合は 403 で拒否する。

    3 の 403 は意図的な仕様変更である。所有者を特定できないまま
    帰属不明のタスクを作る（= 事後に必ず読めなくなる）よりも、
    enqueue 時点で明示的に失敗させるほうが安全で原因も追える。
    """
    if settings.AUTH_DISABLED:
        await _ensure_dev_user_row(db)
        from src.backend.auth import _get_dev_mock_user

        return _get_dev_mock_user()

    try:
        return await get_current_user(token=token, db=db)
    except HTTPException as exc:
        # API キー単独の呼び出しでは所有者が不明。
        # 401 のまま「タスクを投入できたように見える」結果を返さない。
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=(
                "このエンドポイントは所有者を特定できないためタスクを作成できません"
                "（所有者を紐づける Bearer トークンで呼び出してください）"
            ),
        ) from exc


@router.post("/generate", response_model=GenerationResponse)
async def generate_content(
    input_data: EasyModeInput,
    request: Request,
    session=Depends(database.get_db),
    api_key: str = Depends(require_api_key),
    current_user: Any = Depends(get_current_user_or_api_key_owner),
) -> GenerationResponse:
    """章単位の対話型自動生成 [Interactive Writer]"""
    await generate_limiter.check(request)
    try:
        # 所有者を先に解決する（依存 `get_current_user_or_api_key_owner` が
        # 解決できない場合は 403 で弾かれている）。
        owner_id = getattr(current_user, "id", None)

        # 章の中身処理
        processed_chapter = process_chapter(input_data.current_chapter)

        # キャラクター設定を dict に変換
        char_dict = (
            input_data.character_params.model_dump()
            if hasattr(input_data.character_params, "model_dump")
            else dict(input_data.character_params)
)

        # 生成パラメータ準備
        params: dict[str, Any] = {
            "chapter_history": input_data.chapter_history,
            "current_chapter": processed_chapter,
            "character": char_dict,
            "content_length_limit": input_data.content_length_limit,
            "target_episodes": input_data.target_episodes,
            "style_override": input_data.style_override,
            "llm_config": (
                input_data.llm_config.model_dump()
                if input_data.llm_config and hasattr(input_data.llm_config, "model_dump")
                else input_data.llm_config
            ),
            "book_id": input_data.book_id,
            "start_ep": input_data.start_ep,
            "end_ep": input_data.end_ep,
            "compressor": FourLayerCompressor(config=CompressionConfig()),
            # 所有者 ID。 Huey の結果 dict には所有者が含まれないため、
            # `/status/{task_id}` は `_assert_task_ownership(result, ...)` で
            # 判定できず、自分のタスクなのに fail-closed で拒否されてしまう。
            # タスクの入力パラメータ経由で引き継ぎ、結果 dict にも載せる。
            "user_id": owner_id,
        }

        # タスクをキューに投入 (Huey 非同期タスク呼び出し)
        from src.backend.tasks.generation_tasks import generate_chapter_orchestrated_task

        task_result = generate_chapter_orchestrated_task(params)
        huey_task_id = str(task_result.id)
        params["task_id"] = huey_task_id

        # DB レコードを作成
        # user_id を必ず渡すこと。渡さない（NULL）と、同一エンドポイントの
        # `/status/{task_id}` が `_assert_task_ownership` で自分のタスクを拒否する。
        repo = BookRepository(session)
        if repo.is_async:
            await repo.create_task_async(
                task_id=huey_task_id, status="running", user_id=owner_id
            )
        else:
            repo.create_task(task_id=huey_task_id, status="running", user_id=owner_id)

        metrics.increment("tasks_enqueued")
        logger.info("Enqueued generation task: task_id=%s", huey_task_id)

        return GenerationResponse(
            task_id=huey_task_id,
            output="",
            completion_time_ms=0,
            error="",
            suggestions=[
                "生成タスク ID: "
                f"{huey_task_id} を投入しました。"
                f"ステータスを /easy_mode/status/{huey_task_id} で確認してください。"
            ],
        )
    except ValidationError as e:
        logger.warning("Validation error in generate_content: %s", e.errors())
        from src.backend.exceptions import ValidationException

        raise ValidationException(detail=str(e.errors())) from e
    except Exception as e:
        logger.exception("Internal generation error")
        from src.backend.exceptions import ServiceException

        raise ServiceException(detail=str(e)) from e


@router.get("/export/{book_id}")
async def export_easy_mode_package(
    book_id: int = Path(ge=1),
    session=Depends(database.get_db),
    current_user: Any = Depends(get_current_user),
) -> Response:
    """かんたんモードで作成された作品の納品パッケージ (ZIP) をエクスポートする。

    認証済みユーザー本人の作品のみエクスポートできる（他者の book_id を
    推測して差し替えパッケージを取得できないようにする）。
    """
    logger.info("Export requested: book_id=%s", book_id)
    await verify_book_ownership(book_id, current_user)
    metrics.increment("exports_attempted")
    repo = BookRepository(session)
    agent = MarketingAgent(repo=repo)
    zip_bytes, zip_filename = await agent.create_export_package(book_id)

    encoded_filename = urllib.parse.quote(zip_filename)
    # RFC 6266: filename* は UTF-8 パーセントエンコード、filename は ASCII フォールバック
    ascii_filename = zip_filename.encode("ascii", "ignore").decode("ascii") or "export.zip"
    logger.info(
        "Export succeeded: book_id=%s bytes=%d filename=%s",
        book_id,
        len(zip_bytes),
        zip_filename,
    )
    metrics.increment("exports_succeeded")
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


# Task status endpoint
@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the status of a generation task.

    Returns "pending" if not yet completed, "failed" if an error occurred,
    otherwise "completed" with the result.

    認証必須。タスク結果に所有者が記録されている場合は本人 (または管理者) のみ参照できる。
    """
    from src.backend.tasks.huey import huey

    result = huey.result(task_id)

    # タスク結果に user_id が記録されている場合は所有者を確認する
    # （所有者が不明のタスクは管理者だけが参照できる fail-closed 判定）。
    if isinstance(result, dict):
        from src.backend.routers.tasks import _assert_task_ownership

        _assert_task_ownership(result, current_user)

    if result is None:
        logger.info("Task status polled (pending): task_id=%s", task_id)
        return {"task_id": task_id, "status": "pending"}

    if isinstance(result, dict) and result.get("error"):
        logger.info("Task status polled (failed): task_id=%s error=%s", task_id, result["error"])
        return {"task_id": task_id, "status": "failed", "error": result["error"], "result": result}

    logger.info("Task status polled (completed): task_id=%s", task_id)
    return {"task_id": task_id, "status": "completed", "result": result}


@router.delete("/task/{task_id}")
async def cancel_task(
    task_id: str = Path(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$"),
    session=Depends(database.get_db),
    api_key: str = Depends(require_api_key),
) -> dict[str, str]:
    """タスクをキャンセルまたは削除する。"""
    from src.backend.tasks.huey import huey

    # Hueyのタスクを取り消し試行
    try:
        huey.revoke_by_id(task_id)
    except Exception:
        logger.warning("Failed to revoke huey task_id=%s", task_id)

    # DBタスクのステータス更新
    repo = BookRepository(session)
    if repo.is_async:
        await repo.update_task_status_async(task_id, "cancelled")
    else:
        repo.update_task_status(task_id, "cancelled")

    return {"task_id": task_id, "status": "cancelled"}


# --- ガチャ / ダイジェスト / 昇格 エンドポイント ---

from src.domain.entities.easy_mode import (
    DigestRequest,
    DigestResponse,
    ExportRequestPayload,
    GachaRequest,
    GachaResponse,
    PromotionRequest,
    PromotionResponse,
    ReversePlotGeneratePayload,
)
from src.services.digest_service import DigestService
from src.services.gacha_service import GachaService
from src.services.promotion_service import PromotionService


@router.post("/gacha", response_model=GachaResponse)
async def gacha_endpoint(
    req: GachaRequest,
    api_key: str = Depends(require_api_key),
) -> GachaResponse:
    """3案ガチャ企画生成 [Gacha Pitch]"""
    from fastapi import HTTPException


    db = get_db_manager()
    svc = GachaService(db=db)
    try:
        return await svc.generate_plans(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))


@router.post("/digest", response_model=DigestResponse)
async def digest_endpoint(
    req: DigestRequest,
    api_key: str = Depends(require_api_key),
) -> DigestResponse:
    """ダイジェスト生成 [Quick Digest]"""
    from fastapi import HTTPException


    db = get_db_manager()
    svc = DigestService(db=db)
    try:
        return await svc.create_digest(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/promote", response_model=PromotionResponse)
async def promote_endpoint(
    req: PromotionRequest,
    api_key: str = Depends(require_api_key),
) -> PromotionResponse:
    """上級者モード昇格 [Producer Handoff]"""
    from fastapi import HTTPException

    db = get_db_manager()
    svc = PromotionService(db=db)
    try:
        return await svc.promote_book(req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reverse-generate")
async def reverse_generate_endpoint(
    req: ReversePlotGeneratePayload,
    api_key: str = Depends(require_api_key),
) -> dict[str, Any]:
    """逆算プロットビルダー用同期生成エンドポイント [Reverse Plot Builder]"""
    from src.backend.workflows.reverse_plot_workflow import ReversePlotGenerationWorkflow

    workflow = ReversePlotGenerationWorkflow()
    return await workflow.execute(
        reporter=None,
        answers=req.answers,
        target_episodes=req.target_episodes,
        genre=req.genre,
        llm_config=req.llm_config,
    )


@router.post("/export-with-data")
async def export_with_data_endpoint(
    payload: ExportRequestPayload,
    book_id: int = 1,
    session=Depends(database.get_db),
) -> Response:
    """クライアントの最新ステート（本文・設定）を反映して即座にZIPパッケージをエクスポートする"""
    logger.info("Export with custom data requested: book_id=%s title=%s", book_id, payload.title)
    metrics.increment("exports_attempted")

    repo = BookRepository(session)
    # DBにも永続化
    try:
        if repo.is_async:
            await repo.save_or_update_book_with_chapter_async(
                book_id=book_id,
                title=payload.title,
                genre=payload.genre,
                chapter_text=payload.current_text,
                character_params=payload.character,
                plots=payload.plots,
            )
        else:
            repo.save_or_update_book_with_chapter(
                book_id=book_id,
                title=payload.title,
                genre=payload.genre,
                chapter_text=payload.current_text,
                character_params=payload.character,
                plots=payload.plots,
            )
    except Exception as e:
        logger.warning("Failed to auto-save book during export: %s", e)

    agent = MarketingAgent(repo=repo)
    book_data = {
        "title": payload.title,
        "genre": payload.genre,
        "chapters": [
            {
                "ep_num": 1,
                "title": "第1話 運命の覚醒",
                "content": payload.current_text or "本文未入力",
            }
        ],
        "characters": [
            {
                "name": payload.character.get("name", "主人公"),
                "role": "主人公",
                "personality": payload.character.get("personality", "設定なし"),
                "ability": payload.character.get("ability", "設定なし"),
            }
        ]
        if payload.character
        else [],
        "plots": payload.plots
        or [
            {
                "ep_num": 1,
                "title": "第1話 運命の覚醒",
                "one_line_summary": payload.current_text[:100]
                if payload.current_text
                else "冒険の始まり",
            }
        ],
        "bible_settings": {},
    }

    zip_bytes, zip_filename = await agent.create_export_package(book_id, book_data=book_data)

    encoded_filename = urllib.parse.quote(zip_filename)
    ascii_filename = zip_filename.encode("ascii", "ignore").decode("ascii") or "export.zip"
    metrics.increment("exports_succeeded")

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
