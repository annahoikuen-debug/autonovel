# AutoNovel 現況ステータス（SSOT）

最終更新: 2026-09-28
対象: ワークツリー（`E:\ssssad\autonovel`）の実コード

> 本ドキュメントが**現在の実装状況の唯一の正（SSOT）**です。
> ルートの `IMPROVEMENT_SUMMARY.md` / `IMPLEMENTATION_SUMMARY*.md` / `FINAL_SUMMARY.md` などは
> 過去の作業報告のスナップショットであり、現状を表しません。
> 判定は保守的に行い、確認できなかったものは **未確認** と記しています。

---

## 1. バージョン

| 項目 | 値 | 根拠 |
|:---|:---|:---|
| `pyproject.toml` の `project.version`（唯一の正） | **5.3.0** | `pyproject.toml:3` |
| CLI `autonovel --version` | 5.3.0 | `src/cli/main.py` |
| backend `__version__` | 5.3.0 | `src/backend/__init__.py` |
| frontend | 5.3.0 | `frontend/package.json` |
| 直近のリリースノート | `[5.2.1] - 2026-09-26` / `[5.3.0] - 2026-09-28` | `CHANGELOG.md` |

**「v5.2.1」とは何か**: マンガ/low-cost パイプライン統合として記録されたリリースノート上の版（`CHANGELOG.md`）。
現在のコードはすでに 5.3.0（長編耐性・伏線ステートマシン実体化）へ進んでいるため、
**5.2.1 の説明文を現状の根拠に使わないこと**。

---

## 2. ユーザー向け主要機能の実装状況

| 機能 | 状態 | 根拠・理由 |
|:---|:---|:---|
| 小説生成（かんたんモード / easy mode） | **実装済み** | `POST /easy_mode/generate`（`src/backend/routers/easy_mode.py:240`）。`EasyModeWorkflow` が統合パイプラインへ委譲（`src/backend/workflows/easy_mode_workflow.py:53`）。チェックポイント再開あり |
| プロット展開（plot expansion） | **実装済み** | `POST /plots/expand`・`/expand_candidates`・`/expand-beats`（`src/backend/routers/plots.py:86,119,324`）。`plot_expansion_workflow` に配線済み。42ac9e37 で恒常 500 を修正 |
| 執筆（章生成） | **実装済み** | `POST /api/episodes/generate`・`/generate_candidates`・`/retry_failed`・`/chapters/import`（`src/backend/routers/episodes.py`）。統合実装は `src/domain/writing/coordinator.py` |
| ブランチ / IF 経路 | **実装済み** | `src/backend/routers/branches.py` に fork / merge / graph / choices / play セッション / WebSocket。DB は `0015_add_branches_core.py`〜`0016_add_branch_play_sessions.py`。IDOR は 42ac9e37 で修正 |
| 文体比較（style comparison） | **一部実装** | スタイル仕様・プリセット・蒸留・音律整形の API は実装済み（`src/backend/routers/styles.py`）。クライアント側の比較 UI も `wired` 宣言（`frontend/src/capabilities.ts:29`）。ただし「StyleEntry は仕様を返すだけで本文は返さない」（同ファイル:42） |
| 文体適用（style apply to chapter） | **未実装** | `Chapter` モデルにスタイル列が存在しない（`src/backend/database/models.py:244-269`）。`capabilities.ts:33` も `planned` として宣言 |
| 自動改善ループ（auto-improvement） | **未実装** | ループ本体が無い。採点のみ実装（`GET /api/novel/books/{id}/chapters/{n}/score`、`src/backend/database/repositories/book_score.py`）。`src/services/pdca_cycle.py` の `ClosedLoopPDCARunner` は**どこからも import されていない**未配線コード。`capabilities.ts:45` も `planned` |
| 自動書き換え（style rewrite） | **未実装** | スタイル指定の書き換え endpoint が無い。`capabilities.ts:39` が `planned` |
| 公開（なろう） | **部分実装** | `NarouPublisher` は Selenium で実ブラウザ操作（`src/services/publishers/narou.py`）。`POST /publish/{platform}`・`GET /publish/{platform}/preview` で到達可能（`src/backend/routers/publishing.py:41,95`）。**selenium / webdriver-manager は `requirements.txt`・`pyproject.toml` に宣言されていない**ため、素のインストールでは動作しない |
| 公開（カクヨム） | **手動投稿支援のみ** | HTTP 送信は意図的に撤廃。整形済み本文 + 投稿画面 URL の返却のみ（`src/services/publishers/kakuyomu.py:1-7,77`）。自動投稿は行わない |
| 公開（Kindle / KDP） | **部分実装** | LWA OAuth2 + KDP API のクライアントは実装済み（`src/services/publishers/kindle.py`）。ただし KDP API は法人向けアクセス申請が必要で、実利用は未確認 |
| EPUB エクスポート | **実装済み** | `POST /export/ebook` → `/multimedia/ebook` へ委譲（`src/backend/routers/export.py:97-113`）。ビルダは `src/services/exporters/epub_*.py` / `src/services/ebook/epub_generator.py`（依存 `ebooklib` は `pyproject.toml` に宣言済み） |
| 課金 / Stripe | **実装済み（要外部設定）** | `GET /api/billing/plans`・`/balance`・`POST /create-checkout-session`・`/create-portal-session`・`/transactions`（`src/backend/routers/billing.py`）+ webhook（`src/backend/routers/billing_webhook.py`）。`stripe>=11.0.0` は宣言済み。実際の決済疎通は未確認 |
| ヘルスチェック | **実装済み** | `/health/live`・`/health/ready`・`/health/detail`（`src/backend/routers/health.py`）。個別チェックは DB / Redis / ChromaDB / LLM / worker / enrichment agent（`src/backend/health/checks.py`） |
| RAG | **実装済み** | `RAGService`（`src/services/rag/rag_service.py`）。ベクトル検索は pgvector 優先・SQLite/ベクトルストア フォールバック（同ファイル:195-244） |
| GraphRAG | **部分実装** | パイプライン本身は実装（`src/services/graph_pipeline.py`）。ただし `POST /api/graph/upsert-*` 系のグラフ書き込み系は `_graph_write_not_implemented()` を返すスタブ（`src/backend/routers/graph.py:338,355`）。ベクトルストアは `AUTONOVEL_RAG_MODE=auto` で PgVector > Chroma > InMemory の順フォールバック（`src/services/vector_store/__init__.py:41-59`）。PostgreSQL 未整備なら実効は chroma/in-memory |

---

## 3. 現時点で実在する制限（隠さない）

1. **自動改善ループは存在しない。** スコアは採点されるが、スコアに基づく自動書き換えのループは未実装。UI は `capabilities.ts` により無効化されている。
2. **文体の章への適用は存在しない。** `Chapter` テーブルにスタイル列が無い（`src/backend/database/models.py:244`）。文体指定で章を書き直す API も無い。
3. **なろう公開は selenium を要求するが、依存宣言が無い。** `requirements.txt` / `pyproject.toml` に `selenium`・`webdriver-manager` が無く、`src/services/publishers/narou.py` の import が失敗する環境では动车しない。
4. **GraphRAG のベクトルストアは PostgreSQL 無しで chroma / in-memory に落ちる。** `AUTONOVEL_RAG_MODE`（既定 `auto`）で `PgVector > Chroma > InMemory` の順（`src/services/vector_store/__init__.py:41-59`）。グラフ書き込み系は未実装スタブ。
5. **フロントエンドのカバレッジゲートが失敗する。** `frontend/vite.config.*` の thresholds は lines/branches/functions/statements すべて 50% 必須だが、functions の実測は 40%。`npm run test:ci` は失敗する。
6. **`src/services/pdca_cycle.py` / `src/generation/pdca_controller.py` / `src/services/pdca_directive.py` は未配線。** 検索しても他のモジュールから import されない（デッドコード）。
7. **なろう / カクヨム / Kindle の実際の投稿疎通は未確認**（資格情報・外部 API 承認が要るため）。

---

## 4. テストの実行方法と既知の状態

### バックエンド（pytest）

設定は `pytest.ini` に一本化されている（`pyproject.toml` の `[tool.pytest.ini_options]` は削除済み）。
`asyncio_mode = auto`、`testpaths = tests`。

| コマンド | 内容 |
|:---|:---|
| `py -m pytest -q --tb=short` | 全体（`make test`） |
| `py -m pytest tests/unit -q --cov=src --cov-fail-under=40` | ユニット + カバレッジ 40% ゲート（`make test-unit`） |
| `py -m pytest tests/contract -v` | 契約テスト（`make test-contract`） |
| `py -m pytest tests/integration -v` | 統合テスト。PG + Redis 必須（`make test-integration`） |
| `py -m pytest tests/perf -v --benchmark-only` | パフォーマンス（`make test-perf`） |
| `make verify` | lint → format-check → typecheck → black-check → test-unit → test-contract → test-migration |

CI (`.github/workflows/ci.yml`) は `pytest -q -m "not integration and not slow" --timeout=120` を実行する。
`--timeout` は pytest-timeout 導入済み CI 専用の引数で、ローカル既定には入っていない（`pytest.ini` のコメント参照）。

### フロントエンド（vitest）

| コマンド | 内容 |
|:---|:---|
| `npm test` | watch モード（`frontend/package.json`） |
| `npm run test:ci` | `vitest run --coverage`。**カバレッジ閾値で失敗する**（functions 40% < 50%） |
| `make frontend-test` / `frontend-coverage` | Makefile ラッパー |

### 既知の状態（2026-09-28 時点・実行して確認したわけではない）

- 直近のコミットで **契約テストの 401 事故、本番設定バリデーションのテスト汚染、執筆グラフの経路分岐テストの Early Exit 不一致、テストダブルと実装の乖離 4 件、DB 障害時の素の 500** が修正済み。
- 上記の修正が**全て緑になったことは本ドキュメント作成時点では未確認**（テストを実行していない）。
- バックエンドのカバレッジ 40% ゲートの通過可否も **未確認**。

---

## 5. このドキュメントの運用

- 機能を「実装済み」と書くのは、**API 経路が存在し、ディレクトリに配線されている**ことを確認できた場合に限る。未接続のクラスは「未配線」扱いとする。
- 外部ネットワーク・外部サービス・資格情報を要する機能は、コードの記述で判断できる部分だけを記載し、実疎通は **未確認** と明記する。
- 歴史文書（ルートの `*_SUMMARY*.md`、`plans/*.md`）は本ドキュメントより優先度が低い。`plans/` の A1〜A4「96 ステップ」文書は**設計文書**であり進捗の SSOT ではない。
