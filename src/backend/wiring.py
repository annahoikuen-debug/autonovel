"""アプリケーション配線（コンポジションルート）。

レイヤー契約2 のため、正規レイヤー（``src/interfaces`` 等）は旧モノリス
（``src.backend`` / ``src.services``）を import できない。ルーター群・
init_db・エラーハンドラ・認証ミドルウェア・ヘルス/メトリクス・Huey 確認・
プリフェッチ取り消しを本モジュールから ``AppWiring`` として供給する。
"""

from __future__ import annotations

from src.backend.api.admin_phase2 import (
    enrichment_router as admin_enrichment_router,
    rag_router as admin_rag_router,
    router as admin_audit_router,
)
from src.backend.database import init_db
from src.backend.error_handlers import register_error_handlers
from src.backend.middleware.auth_middleware import GlobalAuthMiddleware
from src.backend.observability.health import build_health_payload, metrics
from src.backend.routers import (
    anti_ai,
    annotations as annotations_router,
    auth,
    billing,
    billing_webhook,
    books,
    branches,
    chapters,
    collab,
    commercial,
    commercial_planning,
    cost,
    easy_mode,
    editor,
    episodes,
    export,
    graph,
    # `health` は create_app 内の `/health` エンドポイントとは別物
    # （`/api/health/detail` 等を持つルーター）。operationId の安定のため
    # 関数名は rename しない。
    health as health_router,
    hooks,
    illustrations,
    issues,
    marketing,
    marketing_ctr,
    misc,
    multimedia,
    novel,
    patches,
    pipeline_stream,
    plots,
    projects,
    prompt_compare,
    prompt_versions,
    publishing,
    publishing_assistant,
    orchestrated,
    platform_export,
    stream_writing,
    streaming,
    structure,
    styles,
    subtext,
    system,
    tasks,
    trace,
)
from src.interfaces.api.app_factory import AppWiring, RouterMount


def _huey_check() -> object:
    """Huey タスクキューの生存確認（遅延 import）。"""
    from src.backend.tasks.huey import check_huey_health

    return check_huey_health()


async def _cancel_prefetch() -> int:
    """バックグラウンドの RAG プリフェッチタスクを取り消す（遅延 import）。"""
    from src.services.semantic_cache import cancel_all_prefetch

    return await cancel_all_prefetch()


def build_wiring() -> AppWiring:
    """本番構成の ``AppWiring`` を組み立てる。"""
    return AppWiring(
        routers=(
            RouterMount(easy_mode.router, prefix="/easy_mode", tags=("easy_mode",)),
            RouterMount(easy_mode.router, prefix="/api/wizard", tags=("wizard",)),
            # `/api/easy-mode` はフロントエンドの API 互換エイリアス。環境によって
            # マウント有無が変わると OpenAPI と実ルートが drift するため常時登録する。
            RouterMount(easy_mode.router, prefix="/api/easy-mode", tags=("easy-mode",)),
            RouterMount(streaming.router, prefix="/easy_mode", tags=("streaming",)),
            RouterMount(styles.router),
            RouterMount(graph.router),
            RouterMount(editor.router),
            RouterMount(system.router),
            RouterMount(export.router),
            RouterMount(platform_export.router),
            RouterMount(stream_writing.router),
            # 管理者・監査ルーター登録
            RouterMount(admin_audit_router),
            RouterMount(admin_rag_router),
            RouterMount(admin_enrichment_router),
            # 各ドメインルーターの静的登録
            RouterMount(books.router),
            RouterMount(plots.router),
            RouterMount(episodes.router),
            RouterMount(chapters.router),
            RouterMount(projects.router),
            RouterMount(tasks.router),
            RouterMount(patches.router),
            RouterMount(issues.router),
            RouterMount(marketing.router),
            RouterMount(marketing_ctr.router),
            RouterMount(prompt_versions.router),
            RouterMount(misc.router),
            RouterMount(novel.router),
            RouterMount(commercial.router),
            RouterMount(commercial_planning.router),
            RouterMount(collab.router),
            RouterMount(illustrations.router),
            # Step 19: multimedia プラグインが有効な場合のみマウント
            RouterMount(
                multimedia.router,
                prefix="/multimedia",
                tags=("multimedia",),
                plugin="multimedia",
            ),
            RouterMount(branches.router),
            RouterMount(anti_ai.router),
            RouterMount(cost.router),
            RouterMount(pipeline_stream.router),
            RouterMount(publishing.router, prefix="/api/export"),
            RouterMount(publishing_assistant.router, prefix="/api"),
            RouterMount(auth.router),
            RouterMount(billing.router),
            RouterMount(billing_webhook.router),
            RouterMount(trace.router),
            RouterMount(health_router.router),
            RouterMount(subtext.router),
            RouterMount(annotations_router.router),
            RouterMount(hooks.router),
            RouterMount(prompt_compare.router),
            RouterMount(structure.router),
            RouterMount(orchestrated.router),
        ),
        init_db=init_db,
        register_error_handlers=register_error_handlers,
        auth_middleware=GlobalAuthMiddleware,
        build_health_payload=build_health_payload,
        health_metrics=metrics,
        huey_check=_huey_check,
        cancel_prefetch=_cancel_prefetch,
    )
