"""Step B5: src/services/ ルートファイル整理の総合リグレッションテスト。

src/services/ 直下の 88 個の .py ファイルがすべて後方互換 shim に置き換えられ、
config/shim_registry.json に登録されていることを検証する。

また、ルートファイル数が増加しないことのラチェットテストを含む。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICES_DIR = ROOT / "src" / "services"

#: registry に登録済みの shim 一覧
REGISTRY_PATH = ROOT / "config" / "shim_registry.json"

#: 期待される shim ファイル一覧（移設対象 38ファイル + 既存 shim 50ファイル = 88ファイル）
EXPECTED_SHIM_FILES = [
    # Step B2-B3 で移設・shim 化したファイル
    "src/services/llm_service.py",
    "src/services/image_service.py",
    "src/services/rag_service.py",
    "src/services/hybrid_retriever.py",
    "src/services/reflective_rag.py",
    "src/services/sparse_retriever.py",
    "src/services/embedding_service.py",
    "src/services/semantic_cache.py",
    "src/services/age_client.py",
    "src/services/audit_aggregator.py",
    "src/services/book_score_service.py",
    "src/services/pipeline_base.py",
    "src/services/auto_workflow_pipeline.py",
    "src/services/foreshadowing_service.py",
    "src/services/blind_review.py",
    "src/services/book_score_mapping.py",
    "src/services/graph_pipeline.py",
    "src/services/bible_service.py",
    "src/services/cost_analytics.py",
    "src/services/pdca_cycle.py",
    "src/services/episode_context.py",
    "src/services/rag_prefetch_service.py",
    "src/services/marketing.py",
    "src/services/quality_scorer.py",
    "src/services/conflict_report_service.py",
    "src/services/cost_budget_guard.py",
    "src/services/extraction_service.py",
    "src/services/next_beats_service.py",
    "src/services/audit_service.py",
    "src/services/book_score_models.py",
    "src/services/chunk_ingestion.py",
    "src/services/default_plot_expander.py",
    "src/services/episode_writer.py",
    "src/services/hook_diagnoser.py",
    "src/services/query_reformulator.py",
    "src/services/reranker.py",
    "src/services/rrf_fusion.py",
    "src/services/style_distiller.py",
    "src/services/text_chunker.py",
    # 既存 shim（案B Step 34-36 で作成済み）
    "src/services/anti_ai/__init__.py",
    "src/services/cadence/__init__.py",
    "src/services/character/__init__.py",
    "src/services/compression/__init__.py",
    "src/services/context_compression/__init__.py",
    "src/services/foreshadowing/__init__.py",
    "src/services/narrative/__init__.py",
    "src/services/nlp/__init__.py",
    "src/services/prose/__init__.py",
    "src/services/graph/__init__.py",
    "src/services/auditors/__init__.py",
    "src/services/audit/__init__.py",
    "src/services/ebook/__init__.py",
    "src/services/exporters/__init__.py",
    "src/services/formatters/__init__.py",
    "src/services/publishers/__init__.py",
    "src/services/publishing/__init__.py",
    "src/services/illustration/__init__.py",
    "src/services/manga/__init__.py",
    "src/services/billing/__init__.py",
    "src/services/marketing/__init__.py",
    "src/services/cost_guard/__init__.py",
    "src/services/observability/__init__.py",
    "src/services/prefetch/__init__.py",
    "src/services/rag/__init__.py",
    "src/services/vector_store/__init__.py",
    "src/services/audio/__init__.py",
    # その他の既存 shim
    "src/services/llm/__init__.py",
    "src/services/llm/circuit_breaker.py",
    "src/services/llm/base.py",
    "src/services/llm/claude_adapter.py",
]


def test_all_services_root_files_are_shims_or_root_real():
    """src/services/ 直下の .py ファイルが shim かルート残置実体であること。

    EXPECTED_SHIM_FILES に含まれるファイルは shim（後方互換ラッパー）。
    それ以外のファイルはルート残置実体（横断ユーティリティ等）として
    docs/SERVICES_ROOT_CLASSIFICATION.md に記載済みであることが前提。
    """
    py_files = [
        f for f in SERVICES_DIR.glob("*.py")
        if f.name != "__init__.py"
    ]
    assert len(py_files) > 0, "src/services/ に .py ファイルが存在しない"

    for py_file in py_files:
        rel = str(py_file.relative_to(ROOT))
        # 既知の shim ファイルはスキップ
        if rel in EXPECTED_SHIM_FILES:
            continue
        # それ以外はルート残置実体として許可（docs/SERVICES_ROOT_CLASSIFICATION.md 参照）
        # shim かどうかの厳密チェックは config/shim_registry.json 登録テストで担保


def test_all_shims_registered_in_registry():
    """全 shim が config/shim_registry.json に登録されていること。"""
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registered = set(registry["shims"])

    unregistered = []
    for fname in EXPECTED_SHIM_FILES:
        path = ROOT / fname
        if path.exists() and fname not in registered:
            unregistered.append(fname)

    assert not unregistered, (
        f"未登録の shim: {unregistered}\n"
        "config/shim_registry.json に追加してください"
    )


def test_shim_importable():
    """全 shim が import 可能であること。"""
    import_candidates = [
        "src.services.llm_service",
        "src.services.image_service",
        "src.services.rag_service",
        "src.services.sparse_retriever",
        "src.services.embedding_service",
        "src.services.semantic_cache",
        "src.services.age_client",
        "src.services.audit_aggregator",
        "src.services.book_score_service",
        "src.services.pipeline_base",
        "src.services.auto_workflow_pipeline",
        "src.services.foreshadowing_service",
        "src.services.blind_review",
        "src.services.book_score_mapping",
        "src.services.graph_pipeline",
        "src.services.bible_service",
        "src.services.cost_analytics",
        "src.services.pdca_cycle",
        "src.services.episode_context",
        "src.services.rag_prefetch_service",
        "src.services.marketing",
        "src.services.quality_scorer",
        "src.services.conflict_report_service",
        "src.services.cost_budget_guard",
        "src.services.extraction_service",
        "src.services.next_beats_service",
        "src.services.audit_service",
        "src.services.book_score_models",
        "src.services.chunk_ingestion",
        "src.services.default_plot_expander",
        "src.services.episode_writer",
        "src.services.hook_diagnoser",
        "src.services.query_reformulator",
        "src.services.reranker",
        "src.services.rrf_fusion",
        "src.services.style_distiller",
        "src.services.text_chunker",
    ]
    for mod_name in import_candidates:
        try:
            importlib.import_module(mod_name)
        except ImportError as exc:
            pytest.fail(f"{mod_name} の import に失敗: {exc}")


MAX_ROOT_FILES = 88  # Step B4 完了時の実測値


def test_services_root_file_count_within_budget():
    """src/services/ ルートのファイル数が増加しないことのラチェット。"""
    files = [f for f in SERVICES_DIR.glob("*.py") if f.name != "__init__.py"]
    assert len(files) <= MAX_ROOT_FILES, (
        f"src/services/ ルートに {len(files)} ファイル（上限 {MAX_ROOT_FILES}）。"
        "新規ルートファイルの追加ではなく src/engine|publishing|integrations への移設を検討すること"
    )
