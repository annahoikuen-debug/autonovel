"""ナレッジグラフ可視化・クエリ・GraphRAG操作用 API ルーター."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.backend import database
from src.backend.auth import get_current_user, require_api_key
from src.backend.config import settings
from src.backend.database.models import Character as CharacterModel
from src.backend.database.models import Chapter as ChapterModel, User
from src.backend.security.owner_guard import verify_book_ownership
from src.core.container import AppContainer
from src.domain.schemas.foreshadowing import (
    ForeshadowingGraphResponse,
    GraphEdgeSchema,
    GraphNodeSchema,
)
from src.infrastructure.database.models.chunk import ChapterChunk
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
from src.services.foreshadowing_service import ForeshadowingService
from src.services.graph_pipeline import graph_pipeline_service
from src.services.rag_service import rag_service

router = APIRouter(
    prefix="/api/graph",
    tags=["graph"],
    # 従来は router に認証が無く、GlobalAuthMiddleware を通過した任意のテナントが
    # 他人のナレッジグラフ・チャプター本文を読み書きできた。認証を必須にする。
    dependencies=[Depends(get_current_user)],
)

logger = logging.getLogger("graph_router")


# ============================================================
# 認可ヘルパー
# ============================================================


def _is_admin(user: User | None) -> bool:
    """管理者ロールかどうかを判定する。"""
    return getattr(user, "role", None) == "admin"


async def _assert_chapter_ownership(
    chapter_id: int, current_user: User, session: AsyncSession
) -> None:
    """``chapter_id`` から ``book_id`` を解決して所有権を検証する。"""
    result = await session.execute(select(ChapterModel).where(ChapterModel.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if chapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"チャプターが見つかりません: {chapter_id}",
        )
    await verify_book_ownership(int(chapter.book_id), current_user, session)


async def _require_book_scope(
    book_id: int | None, current_user: User
) -> int:
    """RAG 系で book_id 任意になっている経路の認可を行う。

    ``book_id`` が指定されていれば通常どおり所有権を検証する。
    指定がない場合はセッション（＝全テナント）にまたがる検索になるため、
    管理者に限定する（fail-closed）。
    """
    if book_id is not None:
        await verify_book_ownership(book_id, current_user, AppContainer.db())
        return book_id
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="book_id を指定するか、管理者権限が必要です",
        )
    return book_id  # type: ignore[return-value]


async def _run_blocking(fn: Callable[..., Any], /, **kwargs: Any) -> Any:
    """ブロッキングな **同期** 関数をワーカースレッドへ逃がす。

    ``session`` は同期 ``Session`` であり、内部の `session.execute` /
    `session.query` はループを止める重い I/O になる。そこで **同期コア** を
    ``asyncio.to_thread`` で別スレッドに投げ、メインループは待たされずに済む。

    以前の ``asyncio.to_thread(lambda: asyncio.run(fn(**kwargs)))`` は
    呼び出しごとに新しいイベントループを生成していた（ループ生成コスト、
    ループ所有権の破壊、`tests/regression/test_H1_async_boundary.py` の
    ガード違反）。    それを避けるため `rag_service` / `graph_pipeline_service` は
    同期コア (`*_sync`) を提供しており、ネストしたループを作らずに済む。
    """
    return await asyncio.to_thread(fn, **kwargs)


# ============================================================
# Request/Response Models
# ============================================================


ALLOWED_COLUMN_DEF_PATTERN = re.compile(r"^\s*\(\s*[a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)?(?:\s*,\s*[a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)?)*\s*\)\s*$")


class CypherQueryRequest(BaseModel):
    """任意のCypherクエリ実行リクエスト."""

    query: str = Field(..., description="実行するCypherクエリ")
    graph_name: str | None = Field(None, description="対象グラフ名")
    parameters: dict[str, Any] | None = Field(None, description="クエリパラメータ")
    column_definition: str = Field("(result agtype)", description="戻り値カラム定義")

    @field_validator("column_definition")
    @classmethod
    def validate_column_definition(cls, v: str) -> str:
        if not ALLOWED_COLUMN_DEF_PATTERN.match(v) or any(char in v for char in (";", "-", "/", "\\", "*", "$")):
            raise ValueError("Invalid column_definition format: must be in form '(col_name type, ...)' with no special SQL characters")
        return v


class CypherQueryResponse(BaseModel):
    """Cypherクエリ実行レスポンス."""

    records: list[dict[str, Any]]
    summary: dict[str, Any]
    execution_time_ms: float


class NodeUpsertRequest(BaseModel):
    """ノードUPSERTリクエスト."""

    label: str = Field(..., description="ノードラベル")
    name: str = Field(..., description="ノード名（ユニークキー）")
    properties: dict[str, Any] | None = Field(None, description="追加プロパティ")
    graph_name: str | None = Field(None, description="対象グラフ名")


class EdgeUpsertRequest(BaseModel):
    """エッジUPSERTリクエスト."""

    source_label: str = Field(..., description="始点ノードラベル")
    source_name: str = Field(..., description="始点ノード名")
    target_label: str = Field(..., description="終点ノードラベル")
    target_name: str = Field(..., description="終点ノード名")
    relation_type: str = Field(..., description="関係タイプ")
    properties: dict[str, Any] | None = Field(None, description="関係プロパティ")
    graph_name: str | None = Field(None, description="対象グラフ名")


class BatchUpsertRequest(BaseModel):
    """バッチUPSERTリクエスト."""

    nodes: list[NodeUpsertRequest] = Field(default_factory=list)
    edges: list[EdgeUpsertRequest] = Field(default_factory=list)
    graph_name: str | None = Field(None, description="対象グラフ名")


class BatchUpsertResponse(BaseModel):
    """バッチUPSERTレスポンス."""

    nodes_created: int
    edges_created: int
    errors: list[str] = Field(default_factory=list)


class GraphSearchRequest(BaseModel):
    """グラフ検索リクエスト."""

    node_name: str = Field(..., description="起点ノード名")
    max_depth: int = Field(2, ge=1, le=5, description="最大ホップ数")
    relationship_types: list[str] | None = Field(None, description="フィルタする関係タイプ")
    direction: str = Field("both", pattern="^(outgoing|incoming|both)$", description="方向")
    limit: int = Field(50, ge=1, le=200, description="最大取得件数")
    graph_name: str | None = Field(None, description="対象グラフ名")


class GraphStatsResponse(BaseModel):
    """グラフ統計レスポンス."""

    node_count: int
    edge_count: int
    labels: list[str]
    relationship_types: list[str]


class PipelineProcessRequest(BaseModel):
    """パイプライン処理リクエスト."""

    chapter_id: int = Field(..., description="チャプターID")
    chapter_text: str = Field(..., description="チャプターテキスト")
    idempotency_key: str | None = Field(None, description="冪等性キー")


class PipelineBatchRequest(BaseModel):
    """パイプラインバッチ処理リクエスト."""

    chapters: list[PipelineProcessRequest] = Field(..., min_items=1)
    continue_on_error: bool = Field(True, description="エラー時に継続")


class HybridSearchRequest(BaseModel):
    """ハイブリッド検索リクエスト."""

    query: str = Field(..., description="検索クエリ")
    core_entities: list[str] | None = Field(None, description="グラフ探索の起点エンティティ")
    top_k: int = Field(10, ge=1, le=50, description="返却件数")
    alpha: float = Field(0.5, ge=0.0, le=1.0, description="ベクトル検索の重み")
    beta: float = Field(0.3, ge=0.0, le=1.0, description="グラフ検索の重み")
    gamma: float = Field(0.2, ge=0.0, le=1.0, description="全文検索の重み")
    book_id: int | None = Field(
        None,
        ge=1,
        description=(
            "スコープする書籍ID。検索はセッション全体（=全テナント）にまたがるため、"
            "通常利用では作品所有権の検証に必要なため指定が必須となる"
        ),
    )


class RagContextRequest(BaseModel):
    """RAGコンテキスト生成リクエスト."""

    current_prompt: str = Field(..., description="現在のプロンプト/クエリ")
    character_name: str = Field(..., description="主人公名")
    additional_entities: list[str] | None = Field(None, description="追加エンティティ")
    book_id: int | None = Field(
        None,
        description="対象書籍ID。コンテキストキャッシュのキー的重要组成部分（未指定時はキャッシュを読み書きしない）",
    )


# ============================================================
# Graph Visualization & Query Endpoints
# ============================================================


@router.get("")
async def get_graph_data(
    book_id: int = Query(..., description="作品ID"),
    graph_name: str | None = None,
    session: AsyncSession = Depends(database.get_async_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """フロントエンドの相関図可視化 (Force-Graph 等) 用にノードとエッジ一覧を取得する.

    book_id を指定して、RDBMS (foreshadowings, characters, character_relations) から
    実際の作品データに基づくグラフを動的に生成して返却する。
    """
    # IDOR 防止: 作品の所有権を検証する
    await verify_book_ownership(book_id, current_user, session)
    gname = graph_name or settings.AGE_GRAPH_NAME

    # RDBMSベースの伏線グラフ生成
    foreshadowing_repo = DbForeshadowingRepository(session)
    foreshadowing_service = ForeshadowingService(foreshadowing_repo)

    try:
        # 伏線グラフを取得
        graph_response: ForeshadowingGraphResponse = await foreshadowing_service.get_foreshadowing_graph(book_id)

        # キャラクター情報も追加
        from sqlalchemy import select
        characters = await session.execute(
            select(CharacterModel).where(CharacterModel.book_id == book_id)
        )
        character_list = characters.scalars().all()

        character_nodes = []
        character_edges = []
        for char in character_list:
            node_id = f"character_{char.id}"
            character_nodes.append(
                GraphNodeSchema(
                    id=node_id,
                    label="Character",
                    properties={
                        "name": char.name,
                        "role": char.role,
                        "personality": char.personality,
                        "ability": char.ability,
                    },
                )
            )
            # キャラクターを伏線ノードに接続（同じ作品内なら全伏線に関連付け）
            for f_node in graph_response.nodes:
                if f_node.label == "Foreshadowing":
                    character_edges.append(
                        GraphEdgeSchema(
                            source=node_id,
                            target=f_node.id,
                            type="RELATED_TO",
                            properties={"relation": "character_foreshadowing"},
                        )
                    )

        # すべてのノードとエッジを結合
        all_nodes = graph_response.nodes + character_nodes
        all_edges = graph_response.edges + character_edges

        # キャラクター関係も追加
        from src.backend.database.models_relation import CharacterRelationModel
        char_relations = await session.execute(
            select(CharacterRelationModel).where(CharacterRelationModel.book_id == book_id)
        )
        for rel in char_relations.scalars().all():
            all_edges.append(
                GraphEdgeSchema(
                    source=f"character_{rel.source_char_id}",
                    target=f"character_{rel.target_char_id}",
                    type=rel.relation_type,
                    properties={"description": rel.description} if rel.description else {},
                )
            )

        return ForeshadowingGraphResponse(
            graph_name=gname,
            nodes=all_nodes,
            edges=all_edges,
        ).model_dump()

    except Exception as e:
        logger.error(f"Failed to generate graph for book_id={book_id}: {e}")
        # エラー時はフォールバックデータを返す
        return {
            "graph_name": gname,
            "error": str(e),
            "nodes": [],
            "edges": [],
        }


@router.get("/foreshadowing/kpi")
async def get_foreshadowing_kpi(
    book_id: int = Query(..., description="作品ID"),
    current_episode: int | None = Query(
        None, ge=1, description="現在話数（指定時は期限超過数も計測）"
    ),
    session: AsyncSession = Depends(database.get_async_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """伏線KPI（回収率・未回収数・期限超過数）を取得する。

    v5.3 で追加。ロードマップの主要KPI「伏線回収率」を実測する唯一のAPI。
    同時に Prometheus メトリクス（foreshadowing_collection_rate 等）も更新する。
    """
    from src.services.foreshadowing.kpi import ForeshadowingKpiService

    # IDOR 防止: 作品の所有権を検証する
    await verify_book_ownership(book_id, current_user, session)
    try:
        repo = DbForeshadowingRepository(session)
        kpi = await ForeshadowingKpiService(repo).compute(
            book_id=book_id, current_episode=current_episode
        )
        return kpi.to_dict()
    except Exception as e:
        logger.error(f"Failed to compute foreshadowing KPI for book_id={book_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"伏線KPIの取得に失敗しました: {e}",
        ) from e


@router.get("/chunks")
async def list_chapter_chunks(
    chapter_id: int | None = Query(None, description="章IDでフィルタ"),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(database.get_async_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """保存されているベクトルチャンク一覧を取得する."""
    # チャンク本文は小説の全文を含むため、章の所有者を必ず検証する。
    if chapter_id is not None:
        await _assert_chapter_ownership(chapter_id, current_user, session)
    elif not _is_admin(current_user):
        # chapter_id 未指定は全テナントのチャンクを跨ぐため管理者に限定する
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="chapter_id を指定するか、管理者権限が必要です",
        )

    query = select(ChapterChunk)
    if chapter_id is not None:
        query = query.where(ChapterChunk.chapter_id == chapter_id)
    result = await session.execute(query.order_by(ChapterChunk.created_at.desc()).limit(limit))
    chunks = result.scalars().all()

    return [
        {
            "id": chunk.id,
            "chapter_id": chunk.chapter_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "has_embedding": chunk.embedding is not None,
            "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
        }
        for chunk in chunks
    ]


# ============================================================
# Cypher Query Endpoint
# ============================================================


@router.post("/cypher", response_model=CypherQueryResponse, dependencies=[Depends(require_api_key)])
def execute_cypher(
    request: CypherQueryRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(database.get_db),
) -> CypherQueryResponse:
    """任意のCypherクエリを実行する（管理者向け）.

    呼び出し側が指定した Cypher をそのまま渡せるため、認可は
    GraphRAG の有効無効（インストールフラグ）より **先に** 判定する。
    フラグで無効の場合でも、管理者以外は 403 で拒否する。
    """
    # 認可をフラグ判定より先に行い、無効設定でも攻撃者の取りこぼしを防ぐ
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="このエンドポイントには管理者権限が必要です",
        )

    if not settings.ENABLE_GRAPHRAG or not settings.DATABASE_URL.startswith("postgresql"):
        raise HTTPException(status_code=400, detail="GraphRAG is not enabled or not on PostgreSQL")

    return CypherQueryResponse(records=[], summary="Cypher execution is deprecated/disabled in Relational Memory mode", execution_time_ms=0.0)


# ============================================================
# Graph Mutation Endpoints
# ============================================================


def _graph_write_not_implemented() -> HTTPException:
    """グラフ書き込み系が未実装であることを示す 501 を生成する。

    GraphRAG は "Relational Memory mode" へ移行済みで、ノード/エッジを
    永続化するテーブルもリポジトリも存在しない。従来は書き込みを一切行わず
    `{"success": true}` を返していたため、クライアントは成功と誤認していた。
    """
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Graph node/edge persistence is not implemented. "
            "Relational Memory mode has no graph write store; "
            "use the /api/branches and /api/chapters endpoints instead."
        ),
    )


def _require_graphrag() -> None:
    """GraphRAG が有効かつ PostgreSQL であることを確認する。"""
    if not settings.ENABLE_GRAPHRAG or not settings.DATABASE_URL.startswith("postgresql"):
        raise HTTPException(status_code=400, detail="GraphRAG is not enabled or not on PostgreSQL")


@router.post("/nodes", status_code=201)
def upsert_node(
    request: NodeUpsertRequest,
    session: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """ノードを作成または更新する（未実装）。"""
    _require_graphrag()
    raise _graph_write_not_implemented()


@router.post("/edges", status_code=201)
def upsert_edge(
    request: EdgeUpsertRequest,
    session: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """エッジを作成または更新する（未実装）。"""
    _require_graphrag()
    raise _graph_write_not_implemented()


@router.post("/batch", response_model=BatchUpsertResponse)
def upsert_batch(
    request: BatchUpsertRequest,
    session: Session = Depends(database.get_db),
) -> BatchUpsertResponse:
    """ノードとエッジをバッチで作成・更新する（未実装）。"""
    _require_graphrag()
    # 従来は node_dicts / edge_dicts を組み立てて捨て、去重の上に "作成件数" を
    # 返していた（＝何も書き込まず成功を報告）。永続化先が無いため 501 を返す。
    raise _graph_write_not_implemented()


@router.delete("/nodes/{label}/{name}")
def delete_node(
    label: str,
    name: str,
    graph_name: str | None = Query(None),
    detach: bool = Query(True, description="関連エッジも削除"),
    session: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """ノードを削除する（未実装）。"""
    _require_graphrag()
    raise _graph_write_not_implemented()


# ============================================================
# Graph Search & Traversal Endpoints
# ============================================================


@router.post("/search/neighbors")
def search_neighbors(
    request: GraphSearchRequest,
    session: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """指定ノードからNホップ以内の近傍ノードを取得する."""
    if not settings.ENABLE_GRAPHRAG or not settings.DATABASE_URL.startswith("postgresql"):
        return {"node_name": request.node_name, "neighbors": [], "count": 0}

    neighbors = []

    return {
        "node_name": request.node_name,
        "neighbors": neighbors,
        "count": len(neighbors),
    }


@router.get("/nodes/{node_name}/path/{target_name}")
def get_shortest_path(
    node_name: str,
    target_name: str,
    max_depth: int = Query(5, ge=1, le=10),
    graph_name: str | None = Query(None),
    session: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """2ノード間の最短パスを取得する."""
    if not settings.ENABLE_GRAPHRAG or not settings.DATABASE_URL.startswith("postgresql"):
        raise HTTPException(status_code=400, detail="GraphRAG is not enabled or not on PostgreSQL")

    path = None

    return {
        "source": node_name,
        "target": target_name,
        "path": path,
        "found": path is not None,
    }


@router.get("/stats", response_model=GraphStatsResponse)
def get_graph_stats(
    graph_name: str | None = Query(None),
    session: Session = Depends(database.get_db),
) -> GraphStatsResponse:
    """グラフの統計情報を取得する."""
    if not settings.ENABLE_GRAPHRAG or not settings.DATABASE_URL.startswith("postgresql"):
        raise HTTPException(status_code=400, detail="GraphRAG is not enabled or not on PostgreSQL")

    return GraphStatsResponse(node_count=0, edge_count=0, labels=[], relationship_types=[])


@router.get("/labels")
def get_labels(
    graph_name: str | None = Query(None),
    session: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """グラフ内の全ラベル一覧を取得する."""
    if not settings.ENABLE_GRAPHRAG or not settings.DATABASE_URL.startswith("postgresql"):
        raise HTTPException(status_code=400, detail="GraphRAG is not enabled or not on PostgreSQL")

    return {"labels": []}


# ============================================================
# GraphRAG Pipeline Endpoints
# ============================================================


@router.post("/pipeline/process", response_model=dict[str, Any])
async def process_chapter(
    request: PipelineProcessRequest,
    session: Session = Depends(database.get_db),
    auth_session: AsyncSession = Depends(database.get_async_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """単一チャプターのGraphRAG処理を実行する."""
    # IDOR 防止: 他人のチャプターにナレッジ行を書けないようにする
    await _assert_chapter_ownership(request.chapter_id, current_user, auth_session)

    if not request.chapter_text.strip():
        return {"chunks_created": 0, "entities_created": 0, "relationships_created": 0}

    idempotency_key = request.idempotency_key or f"chapter_{request.chapter_id}"
    # await 漏れにより result が coroutine になっていた（上記 process_chapter 参照）
    # process_chapter_knowledge は LLM 抽出が非同期だが、同期 Session を触る
    # 冪等性チェック・チャンク保存・冪等性記録は内部でワーカースレッドへ
    # 逃が済み（graph_pipeline.py）、ここでさらにループを作らずにそのまま await できる。
    result = await graph_pipeline_service.process_chapter_knowledge(
        session=session,
        chapter_id=request.chapter_id,
        chapter_text=request.chapter_text,
        idempotency_key=idempotency_key,
    )

    return {
        "chapter_id": result.chapter_id,
        "success": result.success,
        "chunks_created": result.chunks_created,
        "entities_created": result.entities_created,
        "relationships_created": result.relationships_created,
        "error": result.error,
        "idempotency_key": result.idempotency_key,
    }


@router.post("/pipeline/batch", response_model=dict[str, Any])
async def process_chapters_batch(
    request: PipelineBatchRequest,
    session: Session = Depends(database.get_db),
    auth_session: AsyncSession = Depends(database.get_async_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """複数チャプターのGraphRAG処理をバッチ実行する."""
    # IDOR 防止: バッチに含まれる全チャプターの所有者を検証する
    for c in request.chapters:
        await _assert_chapter_ownership(c.chapter_id, current_user, auth_session)

    chapters = [(c.chapter_id, c.chapter_text) for c in request.chapters]
    # await 漏れ（process_chapter と同じ原因）
    # チャプター単位のブロッキング処理は process_chapter_knowledge 内部で
    # ワーカースレッドへ逃が済み（process_chapter と同じ理由）
    stats = await graph_pipeline_service.process_chapters_batch(
        session=session,
        chapters=chapters,
        continue_on_error=request.continue_on_error,
    )

    return {
        "chapters_processed": stats.chapters_processed,
        "chunks_created": stats.chunks_created,
        "entities_created": stats.entities_created,
        "relationships_created": stats.relationships_created,
        "errors": stats.errors,
        "elapsed_ms": stats.elapsed_ms(),
    }


@router.get("/pipeline/status")
def get_pipeline_status(
    session: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """パイプラインの処理状態を取得する."""
    return graph_pipeline_service.get_pipeline_status(session)


# ============================================================
# Hybrid Search & RAG Context Endpoints
# ============================================================


@router.post("/rag/hybrid-search")
async def hybrid_search(
    request: HybridSearchRequest,
    session: Session = Depends(database.get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """ハイブリッド検索 (Vector + Graph + Fulltext) を実行する."""
    import time

    # 検索対象はセッション全体なので、作品スコープを必ず指定させる
    await _require_book_scope(request.book_id, current_user)

    start = time.perf_counter()

    try:
        # rag_service は内部で session.execute を同期実行するため、
        # 同期コアをワーカースレッドへオフロードしてイベントループをブロックしない
        results = await _run_blocking(
            rag_service.hybrid_search_sync,
            session=session,
            query=request.query,
            core_entities=request.core_entities,
            top_k=request.top_k,
            alpha=request.alpha,
            beta=request.beta,
            gamma=request.gamma,
        )

        return {
            "query": request.query,
            "results": [
                {
                    "id": r.id,
                    "content": r.content,
                    "metadata": r.metadata,
                    "source": r.source,
                    "score": r.score,
                    "similarity": r.similarity,
                }
                for r in results
            ],
            "count": len(results),
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/context")
async def build_rag_context(
    request: RagContextRequest,
    session: Session = Depends(database.get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """執筆用RAGコンテキスト (グラフ + ベクトル + 全文) を生成する."""
    # book_id 未指定はセッション全体を対象になるため管理者に限定される
    await _require_book_scope(request.book_id, current_user)
    try:
        # rag_service は内部で session.execute を同期実行するため同期コアをオフロードする
        context = await _run_blocking(
            rag_service.build_rag_context_sync,
            session=session,
            book_id=request.book_id,
            current_prompt=request.current_prompt,
            character_name=request.character_name,
            additional_entities=request.additional_entities,
        )

        return {
            "graph_context": context.graph_context,
            "vector_context": context.vector_context,
            "stats": context.stats,
            "token_estimate": context.token_estimate,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/episode")
async def retrieve_for_episode(
    book_id: int | None = None,
    episode_number: int | None = None,
    character_name: str = Query(..., description="主人公名"),
    additional_entities: list[str] | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    session: Session = Depends(database.get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """エピソード執筆向けのコンテキストを一括取得する."""
    # book_id 未指定はセッション全体を対象になるため管理者に限定される
    await _require_book_scope(book_id, current_user)
    try:
        # rag_service は内部で session.execute を同期実行するため同期コアをオフロードする
        result = await _run_blocking(
            rag_service.retrieve_for_episode_sync,
            session=session,
            book_id=book_id,
            episode_number=episode_number,
            character_name=character_name,
            additional_entities=additional_entities,
            top_k=top_k,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/stats")
def get_rag_stats() -> dict[str, Any]:
    """RAGサービスの統計情報を取得する."""
    return rag_service.get_last_stats()


# graph_router エクスポート用
__all__ = ["router"]
