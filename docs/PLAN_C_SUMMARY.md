# 改善案C 実装とりまとめ (PLAN_C_SUMMARY.md)

> **目的**: 案B（36ステップのレイヤー再編）完了後に策定した改善案C
> （`plans/PLAN_C_POST_REORGANIZATION.md`）の実装結果と、併せて実施した
> 公開前デバッグ第1・第2弾の成果を総括する。
>
> **実装期間**: 2026年11月6日〜7日（3コミット: `dfff3d21` → `09530074` → `7e816a87`）

---

## 1. 背景と目的

案B（レイヤー再編36ステップ）で `src/engine/` / `src/publishing/` / `src/integrations/` への
大規模移設を完了した後、以下の3課題が残っていた。

| 課題 | 現状（案B完了時点） | 影響 |
|------|-------------------|------|
| A. tests/ 物理配置 | `tests/` 直下に39個の孤テスト、`tests/services/` 等に旧レイヤー名残存 | テスト発見性・CI |
| B. src/services/ ルート89ファイル | サブパッケージは移設済みだがルート .py が89個残存 | コードレビュー可読性 |
| C. Docker/デプロイ設定 | COPY パス・entrypoint・compose の整合未検証 | デプロイ信頼性 |

---

## 2. 計画（plans/PLAN_C_POST_REORGANIZATION.md）

全15ステップを3フェーズで構成。低性能LLMでも実装できる粒度で、
各ステップに「移動 + shim 作成 + registry 登録 + 参照置換 + import 確認 + テスト」
の手順とリグレッションテストを明記した。

---

## 3. 実装結果

### Phase A: tests/ 物理配置整理 (A1-A6) — ✅ 完了

| Step | 内容 | 結果 |
|------|------|------|
| A1 | tests/ 直下39ファイルの分類表作成 | `docs/TEST_CLASSIFICATION.md` |
| A2 | CI ワークフローのパス参照棚卸し | `docs/CI_PATH_REFERENCES.md`（全6ワークフロー更新不要と判定） |
| A3 | `tests/services/` → `tests/unit/engine/` \| `tests/unit/publishing/` | 105テスト移設・全緑 |
| A4 | `tests/unit/services/` の17サブディレクトリ再配置 | engine(6)/publishing(4)/integrations(3)、1,675テスト移設・全緑 |
| A5 | tests/ 直下39ファイルを適切なサブディレクトリへ | 241テスト移設・収集件数一致 |
| A6 | 総合リグレッション | 全緑 |

**成果**: `tests/` 直下の `test_*.py` が **0件** になり、全テストが
`tests/unit/{レイヤー}/` に整理された。移動先は被テスト対象の import から決定。

### Phase B: src/services/ ルート89ファイル整理 (B1-B5) — ✅ 完了

| Step | 内容 | 結果 |
|------|------|------|
| B1 | 88ファイルの参照数調査と分類表作成 | `docs/SERVICES_ROOT_CLASSIFICATION.md` |
| B2 | バッチ1: LLM・出版・RAG関連9ファイル移設 | `llm_service`→`src/llm/service.py`、`image_service`→`src/publishing/illustration/`、RAG 5ファイル→`src/integrations/rag/` 等 |
| B3 | バッチ2: engine 関連29ファイル移設 | `audit_aggregator`→`engine/audit/`、`book_score_*`→`engine/book_score/`、`pipeline_*`→`engine/` 等 |
| B4 | 残り49ファイルを横断ユーティリティとしてルート残置確定 | 分類表に根拠記載 |
| B5 | 総合リグレッション `test_services_root_unification_complete.py` | 4テスト（shim判定/registry照合/import可否/ルート数ラチェット） |

**成果**:
- 移設対象38ファイルは全て「新パス実体 + 旧パス shim」に移行
- `config/shim_registry.json` に **141 shim** 登録、CI で未登録検出
- `src/services/` ルート数の**ラチェット上限 88** を CI で強制
  （新規ルートファイル追加を禁止し、engine|publishing|integrations への移設を誘導）

### Phase C: Docker・デプロイ設定確認 (C1-C3) — ✅ 完了

| Step | 内容 | 結果 |
|------|------|------|
| C1 | Docker ビルド動作確認 | 本環境に Docker なし → 静的検証で代替 |
| C2 | COPY パス静的検証テスト | `test_docker_copy_paths.py`（5テスト）新規作成 |
| C3 | entrypoint / compose の旧パス参照確認 | 同テストに含む（案B で移動した8パスを stale として監視） |

**成果**: `Dockerfile` / `Dockerfile.prod` の COPY 先6ディレクトリ（src/config/formatters/plugins/prompts/schemas）の実在を CI が保証。
`docker/backend/entrypoint.sh` と `docker-compose*.yml` に旧パス参照がないことを継続監視。

---

## 4. 公開前デバッグ（併施）

### 第1弾（コミット `09530074`）: リファクタ後の不整合解消

| # | 発見した問題 | 修正 |
|---|------------|------|
| 1 | `src/api/{dashboard,conflicts,agent_memory}.py` shim が `set_*_engine` 等の setter を再エクスポートせず、統合テスト4件が収集エラー | shim を `import *` 方式に修正 |
| 2 | `test_p2_architecture_ux_e2e.py` が旧パス `src.core.llm.adapters.mock_unified_client` を参照 | 新パス `src.llm.unified.adapters.mock` に修正 |
| 3 | `frontend/src/types/index.ts` に orchestrated 型の**重複エクスポート**（TS2300 ×8）— 案B Step 29 の編集ミス | 重複ブロック除去、`tsc` 通過・`vite build` 成功を確認 |
| 4 | **`ExecutorManager.shutdown()` の状態漏洩**（最重要）: FastAPI lifespan shutdown がテスト中にシングルトン実エグゼキューターを落とし、後続テストが `cannot schedule new futures after shutdown` で壊れる。テスト移動で実行順序が変わり表面化 | shutdown 後にプールを再作成して冪等化 |
| 5 | `test_hook_diagnoser` の monkeypatch が shim の名前空間コピーに届かない | 実参照先（`src.services.llm_service.LLMService`）に修正 |
| 6 | `test_sqlite_rag_embedding` の monkeypatch が親パッケージ属性（`rag_service` = GraphRAGService インスタンス）を優先解決してしまう | `importlib.import_module` でモジュール解決 |
| 7 | 検出器テスト（`test_writing_quality_loop_no_legacy_import`）のサンプルコードが誤置換 — 検出器テストは旧レイヤー import を**意図的に**含める必要がある | 復旧 |
| 8 | `test_removed_definitions` の PLOT_STRUCTURES 残存チェックが移動したファイルの**コメント**に誤ヒット | コメント行を除外する検索に修正 |

### 第2弾（コミット `7e816a87`）: 事前失敗17テスト全修正

前コミットから存在する失敗17件を原因別に修正。

| ファイル | 件数 | 根本原因 |
|---------|------|---------|
| `test_image_service` | 5 | 実装が旧 `_build_safety_settings` API から `_build_safety_filter_level`（GenAI SDK 文字列マッピング）+ 遅延 import に進化していた。テストを現 API に書き直し。api_key 必須テストは先行テストが設定した `GOOGLE_GENAI_API_KEY` の環境変数漏洩にも対応 |
| `test_setting_delta_merge` | 2 | AsyncMock の子属性は AsyncMock になる仕様で `scalar()` が coroutine を返していた → 同期的 `scalar()` を返す MagicMock を明示設定 |
| `test_negative_learning` | 2 | ChromaDB モックの `metadatas` 構造が逆（`[[辞書]×10]` → `[[辞書×10]]` が正）で negative パターンが1件しかカウントされず、skip 判定が常に無効 |
| `test_genre_mapping` | 1 | `GENRE_REGISTRY`（SSOT）に「ハイファンタジー (R15)」エイリアスが追加されたため期待値更新 |
| `test_patch_review_workflow` | 3 | レガシーコア監査前提のテストに `ENABLE_AUDIT_LEGACY_CORE` 未設定 + UnifiedAuditor が MagicMock LLM を await して即死 → 環境変数有効化 + UnifiedAuditor 無効化 + `extract_keywords` AsyncMock 化 + 現戻り値構造に整合 |
| `test_illustration_router` | 3 | IDOR 対策で後から追加された `verify_book_ownership`（async）が未パッチ → AsyncMock パッチ。Pydantic 検証エラーは FastAPI 標準 422 を期待 |
| `test_scene_continuity_tracker` | 1 | 期待文字列「視点が変更」が実装メッセージに含まれない部分文字列だった |

---

## 5. 最終検証結果

| スイート | 結果 |
|---------|------|
| FastAPI アプリ起動（54ルート） | ✅ |
| wiring / container / CLI / alembic env | ✅ |
| pytest 収集（全9815テスト） | ✅ 収集エラーゼロ |
| `tests/unit` | ✅ **8075 passed, 37 skipped, 9 xfailed, 3 xpassed — 失敗ゼロ** |
| リグレッションスイート（案B+C 統合9ファイル） | ✅ 121 passed |
| フロントエンド `tsc --noEmit` + `vite build` | ✅ |
| Docker COPY パス静的検証 | ✅ 5 passed |

**改善**: 案B 直後の tests/unit 実行で前コミットから失敗していた17件が全修正され、
さらに前コミットで失敗していた9テスト（erotic系5、migrations、plots、p4_async、repository）も
今回の整理で解消された。

---

## 6. 成果物一覧

### 新規作成ドキュメント

| 文書 | 内容 |
|------|------|
| `plans/PLAN_C_POST_REORGANIZATION.md` | 案C 15ステップ計画書 |
| `docs/TEST_CLASSIFICATION.md` | tests/ 直下39ファイルの分類表 |
| `docs/CI_PATH_REFERENCES.md` | CI ワークフローのパス参照一覧 |
| `docs/SERVICES_ROOT_CLASSIFICATION.md` | src/services/ ルート88ファイルの分類表 |

### 新規作成 CI ガードテスト

| テスト | 役割 |
|--------|------|
| `tests/regression/test_services_root_unification_complete.py` | ルートファイルが shim であること・registry 照合・import 可否・**ルート数ラチェット（上限88）** |
| `tests/regression/test_docker_copy_paths.py` | Dockerfile COPY パス実在検証・entrypoint/compose 旧パス監視 |

### 構造変化の最終形

```
src/
├── llm/            ← LLM 統合（clients/, unified/, adapters/, service.py）
├── engine/         ← 生成系 13サブパッケージ + ルート移設ファイル
├── publishing/     ← 出版系 7サブパッケージ + illustration/image_service 等
├── integrations/   ← 外部連携系 8サブパッケージ + rag 系ファイル等
├── backend/routers/← API 統合
├── config/         ← ルート config/ から移設した Python 設定
├── domain/         ← ドメインモデル・スキーマ
└── services/       ← shim のみ（サブパッケージ28個）+ 横断ユーティリティ
tests/
└── unit/           ← 52サブディレクトリに整理、直下の孤テスト 0件
config/
└── YAML 設定ファイルのみに純化
```

---

## 7. 残タスクと推奨事項

| 項目 | 優先度 | 内容 |
|------|--------|------|
| 統合・e2e テストの緑化 | 中 | 2026-11-08 時点で **9 failed / 336 passed / 37 skipped**（54 failed + 36 errors から改善）。残り9件は深いロジック系（伏線解析 NLP・世代タスク・degrade スコアとゲート閾値の整合等）で個別調査が必要。**状態: 未達**。CI `integration-observe` は `continue-on-error: true` で「未達」を意味し、ゲート化は plans/PLAN_GATE_INTEGRATION_24STEPS.md（Step 21: CI 実測 → Step 22: continue-on-error: false 切り替え）に従う。「観測モード」と呼ぶことは禁止（docs/TEST_GATE_POLICY.md）。 |
| shim 削除計画の Phase R0+R1 | ✅ 完了 | 141 shim 全てに DeprecationWarning 付与（`47e5c9d3`）。R1 検証テスト・R0 観測基盤（`test_shim_deprecation_warning.py` / `test_shim_usage_stats.py`）追加。R2（参照解消）以降は `docs/SHIM_REMOVAL_PLAN.md` に従う |
| `tests/unit` 重複ディレクトリ統合 | ✅ 完了 | `llm_clients/` 削除、`*_src_backup` 3ディレクトリ統合（270テスト）、`agent/` → `agents/` 統合（18テスト）。収集件数 8124 損失なし（`a4012811`） |
| Docker 実ビルド検証 | 低 | Docker 導入環境で `docker build` を1回実行し、C1 のフォールバック検証を補完 |

### 統合テスト緑化の主な修正（2026-11-08、コミット `f142c516`〜）

**プロダクションバグ修正（テストが正しく発見）**:
- `BookRepository.get_book_by_id` 欠落 → **IDOR 対策の 403 経路が壊れていた**（book.py に実装追加）
- `get_all_plots` 旧 API 呼び出し（位置引数に branch_id、keyword に book_id が二重定義 → TypeError）を `marketing.py` / `export_package.py` で修正
- `generation_tasks` の `CreditService.deduct_credits` **await 漏れ**（async 化に未追従）を修正
- マイグレーション複数バグ: 0033 `_rebuild_table`（Constraint 混在で c.name=None → TypeError）、0032/0034（SQLite は FK 名を保存しないため downgrade の drop_constraint が失敗 → naming_convention 明示）、0025/0018/0021/0022/0024（create_all フォールバック DB でインデックス有無がずれる → 存在チェック付き drop_index）
- `PlanStep` が `ctx.easy_parameters` を丸ごと再構築し前段の官能パラメータを破壊 → マージ方式に修正
- `MarketingAgent` の fallback 経路復旧（repo 未指定時は DEFAULT_FALLBACK、repo あり不存在時は ValueError）

**テスト側の整合（実装の仕様変更に追従）**:
- `verify_book_ownership` の NULL user_id 拒否 → seed に user_id 追加
- FastAPI 0.162 の `_IncludedRouter`（遅延解決）→ `app.openapi()["paths"]` ベースの検証に移行
- `build_fused_emotional_context_prompt` 第2引数誤用 → キーワード引数に修正、annotation 優先契約は `highest_confidence` モード注入で検証
- `create_hegemony_plan` キーワード引数呼び出し → kwargs で検証
- 12ステップ固定ビート廃止（Spine ベース生成）・LLM 呼び出し失敗は 502（縮退しない）に追従
- 案A で移動した bat のパス更新（`scripts/windows/`）

---

## 8. まとめ

案Cは「案B の後に残った3課題」を15ステップで完遂し、加えて公開前に
リファクタ後の不整合8件・事前失敗17件を修正した。結果として：

- **テストの発見性**: `tests/` 直下の孤テスト 0件、52サブディレクトリに整理
- **`src/services/` の肥大化防止**: ルート数ラチェット（上限88）を CI で強制
- **デプロイ信頼性**: Docker COPY パス・旧パス参照を CI が継続監視
- **テスト品質**: 事前失敗ゼロ化（8075 passed / 失敗 0）とモック不備の構造的修正
- **後方互換**: 全旧 import 経路が shim で維持され、141 shim が registry で管理

既存コードは import を変更せずに動作し続け、新規コードは正規レイヤー
（`engine` / `publishing` / `integrations` / `llm`）を直接使う状態になった。

---

## 8. lint バジェットのバーンダウン転換（2026-11-08、コミット `215f1266`）

評価で指摘された「mypy 1,122件を約6週間上限固定する形骸化」を解消した。

### 仕組み（config/ci_lint_baseline.json + scripts/ci_lint_ratchet.py）

| ルール | 挙動 |
|--------|------|
| 現在値 > baseline | fail（悪化検出・従来どおり） |
| 現在値 < baseline | baseline を自動的に下げる（ratchet） |
| 期限切れマイルストーン未達 | **fail**（新規：期限付きバーンダウン強制） |
| baseline が期限切れ target より緩い | target まで強制引き下げ |

### マイルストーン

| milestone | metric | target | 期限 |
|-----------|--------|--------|------|
| mypy-half | mypy_errors | 567 | 2026-11-30 |
| mypy-quarter | mypy_errors | 284 | 2026-12-31 |

### 第1弾の成果（1,134 → 952、-182件）

- ortools の mypy override（CpModel 動的束縛の誤検出 23件）
- `IPlotRepository.get_by_id` / `IWorldBibleRepository` novel-scoped API 追加（Protocol 不備 50件+）
- `verify_book_ownership` が AsyncSession を受けられる拡張（**呼び出し側セッションが無視され本番 DB を見る実バグ修正**、11件）
- var-annotated 85件・rowcount 9件・None ガード等

### 同時解消

- **format 867 → 0**（ruff format 一括実行、759件の未整形負債消滅）
- ruff 90 → 85（chromadb fixture の未定義変数等は実バグ修正）

### 残山（mypy-half 達成のための計画）

| 残山 | 件数 | 解消計画 |
|------|------|---------|
| Column 系（assignment/arg-type/return-value） | 約190 | `Mapped[T] = Column(...)` 注釈付与（runtime 不変・機械変換可、要テスト検証） |
| union-attr | 95 | Optional ガード挿入（None 時の契約を個別判断） |
| arg-type / attr-defined | 250 / 170 | 個別修正（実バグ混在のため慎重に） |

### 注意

- 並行で進行中の巨大ファイル分割（audit_agent / book_score パッケージ化）が
  `tests/regression/test_t6_plan_completion.py` の S7 完了条件を一時的に NG にしている。
  分割完了後に再確認すること。
