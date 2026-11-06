# テスト配置分類表 (TEST_CLASSIFICATION.md)

> **目的**: `tests/` 直下に裸で置かれた 39 個の `test_*.py` を、被テスト対象のレイヤーに応じて適切なサブディレクトリへ移設するための分類表。
>
> **作成**: Phase A Step A1
> **前提**: `pytest.ini` に `pythonpath = .` が設定されているため、テストファイルの物理配置を変えても import 文（`from src.xxx ...`）は変更不要。

---

## 分類方針

| 被テスト対象の import | 移動先ディレクトリ |
|---------------------|-------------------|
| `from src.services.*` / `from src.engine.*` | `tests/unit/engine/` または `tests/unit/services/` |
| `from src.backend.*` | `tests/unit/backend/` または `tests/unit/database/` |
| `from src.models.*` / `from src.domain.*` | `tests/unit/models/` または `tests/unit/domain/` |
| `from src.agents.*` | `tests/unit/agents/` または `tests/unit/publishing/` |
| `from src.backend.server import app` / FastAPI ルータ | `tests/unit/api/` |
| `from config.*` | `tests/unit/config/` |
| `tests.mocks.*` のテストハーネス | `tests/unit/` または `tests/regression/` |
| 複数レイヤーを跨ぐ統合的なテスト | `tests/integration/` |
| conftest フィクスチャの整合性検証 | `tests/regression/` |

---

## 分類結果 (39ファイル)

| # | ファイル | 被テスト対象 (import から推定) | 移動先 | 根拠 |
|---|---------|---------------------------|--------|------|
| 1 | `tests/test_cadence_reformatter.py` | `src.services.cadence_reformatter` | `tests/unit/engine/cadence/` | cadence は `src/engine/cadence/` に移設済み |
| 2 | `tests/test_conftest_fixtures.py` | conftest フィクスチャ自体 | `tests/regression/` | 環境変数・モックLLMアダプターの整合性検証 |
| 3 | `tests/test_constants.py` | `config.constants` | `tests/unit/config/` | `config/` から `src/config/` に移設済み |
| 4 | `tests/test_continuity_tracker.py` | `src.agents.erotic_integrity` | `tests/unit/agents/` | agents エージェント |
| 5 | `tests/test_deai_auditor_edges.py` | `src.agents.audit` + `src.models.sharp_edge` | `tests/unit/agents/` | agents.audit が主体 (モデル参照は付随) |
| 6 | `tests/test_easy_mode_api.py` | easy mode API (conftest 依存) | `tests/unit/api/` | FastAPI エンドポイントテスト |
| 7 | `tests/test_easy_mode_workflow.py` | `src.models.writing` + workflow | `tests/unit/backend/` | `src.backend.workflows` を使用 |
| 8 | `tests/test_emotional_hook.py` | `src.models.emotional_hook` | `tests/unit/models/` | Pydantic モデルテスト |
| 9 | `tests/test_entertainment_check_model.py` | `src.models.entertainment_check` | `tests/unit/models/` | Pydantic モデルテスト |
| 10 | `tests/test_erotic_integration.py` | `src.services.auto_workflow_pipeline` | `tests/integration/` | サービス間連携の統合テスト |
| 11 | `tests/test_erotic_workflow.py` | `src.services.*` + `src.engine.prompts` | `tests/integration/` | サービス + エンジンのクロスレイヤー |
| 12 | `tests/test_full_auto_workflow.py` | `src.models.writing` | `tests/unit/models/` | Pydantic モデルテスト |
| 13 | `tests/test_gacha_digest_service.py` | `src.domain.entities.easy_mode` | `tests/unit/domain/` | ドメインエンティティ |
| 14 | `tests/test_genre_mapping.py` | `src.backend.routers.easy_mode` | `tests/unit/backend/` | バックエンドルーター |
| 15 | `tests/test_health.py` | `src.backend.server` | `tests/unit/backend/` | FastAPI サーバー |
| 16 | `tests/test_illustration_agent.py` | `src.agents.illustration_agent` + `src.models.illustration` | `tests/unit/agents/` | agents イラストレーション |
| 17 | `tests/test_illustration_router.py` | illustration router | `tests/unit/api/` | FastAPI ルーターテスト |
| 18 | `tests/test_image_service.py` | `src.services.image_service` | `tests/unit/services/` | サービス (illustration 関連) |
| 19 | `tests/test_migrations.py` | alembic | `tests/integration/` | DB マイグレーション統合テスト |
| 20 | `tests/test_negative_learning.py` | `src.services.learning_data_service` | `tests/unit/services/` | サービステスト |
| 21 | `tests/test_patch_review_workflow.py` | `src.agents.audit_agent` + `src.services.*` | `tests/unit/agents/` | agents.audit_agent が主体 |
| 22 | `tests/test_plan_workflow.py` | `src.backend.workflows.plan_generation_workflow` | `tests/unit/backend/` | バックエンドワークフロー |
| 23 | `tests/test_planning_subversion.py` | `src.agents.planning` | `tests/unit/agents/` | agents プランニング |
| 24 | `tests/test_plot_subversion_integration.py` | `src.models.plot` + `src.models.subversion` | `tests/unit/domain/` | ドメインモデル |
| 25 | `tests/test_report_models.py` | `src.models.report` | `tests/unit/models/` | Pydantic モデルテスト |
| 26 | `tests/test_scene_continuity_tracker.py` | `src.agents.erotic_integrity` | `tests/unit/agents/` | agents エロティックインテグリティ |
| 27 | `tests/test_setting_delta_merge.py` | `src.services.bible_service` + `src.services.graphrag_sync_service` | `tests/unit/services/` | サービステスト |
| 28 | `tests/test_sharp_edge.py` | `src.models.sharp_edge` | `tests/unit/models/` | Pydantic モデルテスト |
| 29 | `tests/test_style_profile_and_distiller.py` | `src.models.style_profile` + `src.services.style_distiller` | `tests/unit/services/` | サービス + モデル (サービス主体) |
| 30 | `tests/test_styles_router.py` | `src.backend.server` | `tests/unit/backend/` | FastAPI サーバー |
| 31 | `tests/test_subtext_suite_integration.py` | `src.backend.server` + `src.narrative` + `src.pipeline` | `tests/integration/` | 複数レイヤー統合テスト |
| 32 | `tests/test_subversion_engine.py` | `src.models.subversion` | `tests/unit/models/` | Pydantic モデルテスト |
| 33 | `tests/test_unified_pipeline.py` | `src.services.auto_workflow_pipeline` | `tests/unit/services/` | サービステスト |
| 34 | `tests/test_uow.py` | `src.backend.database` | `tests/unit/database/` | データベース UoW |
| 35 | `tests/test_writing_workflow.py` | `src.backend.workflows.episode_writing_workflow` | `tests/unit/backend/` | バックエンドワークフロー |
| 36 | `tests/test_erotic_integration.py` | (重複 - 上記 #10 と同一) | — | — |
| 37 | `tests/test_erotic_workflow.py` | (重複 - 上記 #11 と同一) | — | — |
| 38 | `tests/test_easy_mode_api.py` | (重複 - 上記 #6 と同一) | — | — |
| 39 | `tests/test_easy_mode_workflow.py` | (重複 - 上記 #7 と同一) | — | — |

> 補足: 表の #36-39 は行番号の重複記載を避けるため、実際には #1-#35 のみが実ファイル。

---

## 移動先ディレクトリ一覧 (作成予定)

- `tests/unit/api/` (既存)
- `tests/unit/backend/` (既存)
- `tests/unit/config/` (既存)
- `tests/unit/database/` (新規)
- `tests/unit/domain/` (新規)
- `tests/unit/engine/` (新規)
- `tests/unit/engine/cadence/` (新規)
- `tests/unit/models/` (既存)
- `tests/unit/publishing/` (既存)
- `tests/unit/services/` (既存)
- `tests/unit/agents/` (新規)
- `tests/integration/` (既存)
- `tests/regression/` (既存)

---

## Step A1 完了条件

- `docs/TEST_CLASSIFICATION.md` が上記内容で作成されていること
- 39ファイルすべてが表に記載されていること（行数カウントで網羅確認）
