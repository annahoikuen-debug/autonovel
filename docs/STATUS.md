# AutoNovel 現況ステータス（SSOT）

最終更新: 2026-09-30
対象: ワークツリー（`E:\ssssad\autonovel`）の実コード

> 本ドキュメントが**現在の実装状況の唯一の正（SSOT）**です。
> ルートの `IMPROVEMENT_SUMMARY.md` / `IMPLEMENTATION_SUMMARY*.md` / `FINAL_SUMMARY.md` などは
> 過去の作業報告のスナップショットであり、現状を表しません。
> 判定は保守的に行い、確認できなかったものは **未確認** と記しています。

---

## 1. バージョン

| 項目 | 値 | 根拠 |
|:---|:---|:---|
| `pyproject.toml` の `project.version`（唯一の正） | **6.0.0** | `pyproject.toml:3` |
| CLI `autonovel --version` | 6.0.0 | `src/cli/main.py` |
| backend `__version__` | 6.0.0 | `src/backend/__init__.py` |
| frontend | 6.0.0 | `frontend/package.json` |
| 直近のリリースノート | `[6.0.0] - 2026-09-28` | `CHANGELOG.md` |

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
5. **フロントエンドの `npm run test:ci` は失敗する（2026-10-02 実測）。** 原因はカバレッジ閾値ではなく **6 ファイル / 9 テストの失敗**（`tests/unit/uiux/wizardStep3Editing.test.tsx` ほか。vitest はテスト失敗時に coverage レポートを書き出さないため、現在の主ゲートは閾値ではない）。`frontend/vite.config.ts` の thresholds は lines/branches/functions/statements すべて 50% のままである（D07: 閾値は本次計画で上げない。`src/types/**` の除外は「正直な表示」のため維持する）。カバレッジの実測値は 9 件のテスト失敗が直るまで取得できない。
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
| `make verify` | lint → format-check → typecheck → test-unit → test-contract → test-migration |

CI (`.github/workflows/ci.yml`) は `pytest -q -m "not integration and not perf and not slow" --timeout=120` を実行する。
`--timeout` は pytest-timeout 導入済み CI 専用の引数で、ローカル既定には入っていない（`pytest.ini` のコメント参照）。

### フロントエンド（vitest）

| コマンド | 内容 |
|:---|:---|
| `npm test` | watch モード（`frontend/package.json`） |
| `npm run test:ci` | `vitest run --coverage`。**2026-10-02 実測で 6 ファイル / 9 テストが失敗する**ため coverage レポートが生成されず、閾値ゲートには到達しない |
| `make frontend-test` / `frontend-coverage` | Makefile ラッパー |

### 既知の状態（2026-09-28 時点・実行して確認したわけではない）

- 直近のコミットで **契約テストの 401 事故、本番設定バリデーションのテスト汚染、執筆グラフの経路分岐テストの Early Exit 不一致、テストダブルと実装の乖離 4 件、DB 障害時の素の 500** が修正済み。
- 上記の修正が**全て緑になったことは本ドキュメント作成時点では未確認**（テストを実行していない）。
- バックエンドのカバレッジ 40% ゲートの通過可否も **未確認**。

### 2026-10-02 再実測（PLAN_H1_SECURITY_HYGIENE_36STEPS の受入時）

| 対象 | 実測 |
|:---|:---|
| `py -m pytest tests/regression` | 4 failed / 263 passed（内訳は §8 参照。4 件は本計画開始前から赤） |
| `py -m pytest tests/security` | 緑 |
| `npm run test:ci` | 6 files / 9 tests 失敗（`functions` 閾値に到達しない） |
| `npm run typecheck` | 緑（エラー 0） |
| `/health` | 200 |
| ruff | ratchet 化済み（`scripts/ci_lint_ratchet.py`）。ベースライン 0 化は別計画（N1） |

---

## 5. v6 効果測定【2026-09-29 実測】

以下は `PLAN_T6_REMEDIATION_18STEPS.md` Step 13-14 で**機械的に実測**した値である。
推測値は記載していない。未計測の項目は `未計測` と明記する。

### 5.1 1話あたりの LLM 呼び出し回数

| 指標 | 現状 | 目標 | 実測 | 判定 |
|:---|:---|:---|:---|:---|
| 1話あたり LLM 呼出回数 | 10 | 4-5 | **10** | **未達** |
| 1話あたり推定コスト | — | 大幅減 | **$0.00126310**（197 tokens） | 参考値 |
| 構成推計 vs 実測の乖離 | — | — | 10 対 10（差 ±0） | 一致 |

- 出典: `tests/perf/test_v6_llm_call_budget.py`
- **測定条件**: 決定的なスタブ LLM。実ネットワークのレイテンシ・コストは含まない。
- **注記**: 「構成推計」（`STRUCTURAL_SKILL_LLM_CALLS`）は構造から読み取った想定値であり、
  効果測定には**用いない**。実測値（トラッカーの実カウンタ）のみを記載した。
- **未達の原因**: v5.0 で 8 名並列オーディター呼び出しを廃止し、**二層ハイブリッド監査（UnifiedAuditor）** に一本化。第1層 静的ルール解析（0ms/0円）+ 第2層 単一LLM定性評価により、LLM 呼出回数は 1話あたり 1 回に削減。ただし第2層の LLM 呼出が監査フェーズのボトルネックとなり、1話あたりの LLM 呼出回数目標 4-5 回に対して実測 10 回（うち監査が支配的）となっている。軽量監査モードによるさらなる削減は別計画。

### 5.2 監査レイテンシ（二層ハイブリッド監査の効果）

| 指標 | 目標 | 実測 | 判定 |
|:---|:---|:---|:---|
| 第1層 静的ルール解析 | 0ms | **0.144 ms**（中央値, 5回） | — |
| 第2層 単一LLM定性評価 | LLM 1 回呼出 | **0.300 ms**（中央値, 5回、スタブLLM） | **ネットワーク I/O 支配時は未計測** |

- 出典: `tests/perf/test_v6_audit_latency_and_regen.py::test_audit_latency_measured_parallel_vs_serial`
- **測定条件**: 決定的なスタブ LLM = **I/O 待ちが無い**。この条件では LLM 呼出オーバーヘッドが支配的。
- **重要**: 本番のように**ネットワーク I/O が支配的な**場合の短縮率は **未計測**（実 API を叩く必要があるため）。本表の数値で効果を断定してはならない。

### 5.3 本文再生成比率（ゲート集約 Step 23 の効果）

| シナリオ | 再生成比率 | aggregate_score | gate mode |
|:---|:---|:---|:---|
| 二層ハイブリッド監査 不合格（最悪ケース） | **100%** | 39.23 | `score_aggregation` |
| 軽微1件のみ不合格 | **0%**（`should_retry=False`） | — | `score_aggregation` |

- 出典: `tests/contract/test_v6_audit_gate_thresholds.py` / `tests/perf/test_v6_audit_latency_and_regen.py`
- **ゲート集約の効果は実測で確認できた**。
  all-or-nothing ゲートとの実測比較: **再執筆率 100% → 11%**（9パターン中1件のみ再執筆）。
- **10%未満の目標**: 確率的コーパス（`reject_threshold=0.20`）での比率は
  `tests/perf/test_v6_audit_failure_rate.py` が担当するが、当該テストは
  **STUB 校正値**を含むため、効果測定表の主指標には採用していない（参考値）。

### 5.4 未計測の項目

| 指標 | 状態 | 理由 |
|:---|:---|:---|
| 実ネットワークでの監査レイテンシ短縮率 | **未計測** | 実 API 呼び出しが必要 |
| 本番データでの1話コスト | **未計測** | 計測 DB が本リポジトリに含まれない |
| 長編完走率 | **未計測** | 実作品データが必要 |
| 伏線回収率（KPI） | **未計測** | 実作品データが必要 |

コストの内訳は `scripts/report_episode_cost.py` で出力できる
（`--db <sqlite> --json`）。ただし計測 DB がないため本環境では空になる。

### 5.5 投機的プリフェッチの効率化（W6 完了 / 2026-09-30）

`PLAN_W6_PREFETCH_CANCELLATION_12STEPS.md` の 12 ステップを実装済み。
W6 の実害は「遅い」ことではなく **「無駄な課金が静かに続ける」** ことだった。

| 項目 | 実装内容 | 根拠 |
|:---|:---|:---|
| タスク管理の一本化 | `PrefetchRegistry`（key → Task）を新設。`cancel` / `cancel_prefix` / `stats` のみ公開 | `src/services/prefetch/registry.py` |
| 協力的キャンセル | `CancellationToken`（`asyncio.Event` ベース）を新設。リポジトリ初の協力的トークン | `src/core/cancellation.py` |
| `asyncio.coroutine` 撤去 | Python 3.11 で削除済み API の 3 箇所を `_null()` へ置換。**プリフェッチの恒久 no-op を解消** | `src/services/rag_prefetch_service.py:22-32` |
| 投機プロンプト生成の既定 OFF | `ENABLE_SEMANTIC_PREFETCH_DRAFT`（既定 `0`）。リテイク時の無駄な embedding 費をゼロ化 | `src/services/semantic_cache.py` `is_draft_prefetch_enabled()` |
| 静的ナレッジ限定 | `prefetch_for_episode(..., static_only=True)` を追加（既定 `False` で既存挙動を維持） | `src/services/rag_prefetch_service.py` |
| 全経路キャンセル API | `cancel_all_prefetch()` / `close_background_tasks()` / `RagPrefetchService.cancel_all()` / `.close()` | `src/services/semantic_cache.py`, `src/services/rag_prefetch_service.py` |
| shutdown 配線 | FastAPI `lifespan` を `try/finally` 化し、プリフェッチ取り消しと `executor_manager.shutdown()` を実行 | `src/backend/server.py` lifespan |
| ハンドル保持 | `episode_writing_workflow._prefetch_tasks` / `episode_writer._plot_prefetch_tasks` で保持し、完了時に自動片付け | 各 `_trigger_prefetch` / `_track_plot_prefetch` |
| イベント系からの取り消し | `POST /api/episodes/retry_failed` → `cancel_prefix(book_id)`、`POST /api/tasks/{id}/stop` → `cancel_all_prefetch()` | `src/backend/routers/episodes.py`, `src/backend/routers/tasks.py` |
| 投機実行ゲート | `should_speculate()` 純関数。`ENABLE_SPECULATIVE_PREFETCH=1` かつ自動モード かつ監査スコア ≥ `PREFETCH_MIN_AUDIT_SCORE`（既定 90）のときだけ投機 | `src/backend/workflows/episode_writing_workflow.py` |

ロールバックは環境変数 1 つで可能（`ENABLE_SEMANTIC_PREFETCH_DRAFT` / `ENABLE_SPECULATIVE_PREFETCH` / `PREFETCH_MIN_AUDIT_SCORE`）。

### 5.6 監査の外科的スパンリライト（W4 完了 / 2026-09-30）

`PLAN_W4_SURGICAL_PATCH_12STEPS.md` の 12 ステップを実装済み。
「1 オーディターでも落ちたらエピソード全文再執筆」を
**静的ルール即時置換 → 段落単位スパン置換 → シーン再生成** の三段階トリアージに置き換えた。

| 項目 | 実装内容 | 根拠 |
|:---|:---|:---|
| 静的ルールの重大度 | `Issue.severity`（既定 `minor`、最終フィールド追加で位置引数3つ生成を保持） | `src/audit/static_rules.py` |
| 三段階トリアージ | `TRIAGE_MINOR/MEDIUM/MAJOR` の純関数 2 つ（`Issue` のみに依存、LLM 禁止） | `src/audit/triage.py` |
| 段落的文字オフセット | `ParagraphIndexer` がオフセットを返す（コメントアウトされていた W5-05 の再確立） | `src/services/prose/paragraph_indexer.py` |
| 弱段落の特定 | `TargetedDiagnostic` の未実装スタブを実装（`ClosedLoopPDCARunner` の段落パッチ経路が到達可能に） | `src/services/audit/targeted_diagnostic.py` |
| 決定論的スパン置換 | `SpanPatchApplier`（`apply` / `apply_all`） | `src/services/prose/span_patch_applier.py` |
| 検証付き LLM スパンパッチ | `LocalPolisher.polish_span`（差し替えを検証してから本文へ反映） | `src/generation/local_polish.py` |
| 修復計画の三段階判定 | `plan_repair(text, outcomes, static_issues)` → `none` / `span` / `scene` | `src/audit/repair_planner.py` |
| 外科的パスの配線 | `try_local_patch` の 3 段フォールバックの間に `span` 段を挿入。`SafeReplacer` と `actionable_patch` は無改変 | `src/agents/audit_agent.py` |
| Advisory 警告通過帯 | `AUDIT_ADVISORY_THRESHOLD`（既定 80.0）＋ `AUDIT_GATE_ADVISORY_SEVERITIES` | `src/agents/audit_agent.py` `evaluate_gate` |
| 全滅の予算化 | `PDCAController(max_regenerations=1, max_local_patches=3)` を配線（1話あたり Branch D は最大 1 回） | `src/agents/audit_agent.py` |
| パッチ観測点 | `audit.patch.applied`（4キー）/ `audit.patch.skipped`（`reason` 1キー）/ `audit.regeneration.full`（`attempt`）をリングバッファへ発火 | `src/agents/audit_agent.py` `emit_event` |

ロールバックは環境変数 1 つで可能（`ENABLE_AUDIT_SPAN_PATCH` / `ENABLE_AUDIT_POLISH_ASYNC` / `ENABLE_AUDIT_REPAIR_BUDGET` / `ENABLE_AUDIT_SCORE_GATE` / `ENABLE_AUDIT_LOCAL_PATCH`）。

### 5.7 同時に修正した実バグ（残存 failures の実因追跡で判明）

| バグ | 実因 | 修正 | 根拠 |
|:---|:---|:---|:---|
| advisory ゲートが手動厳格化を消す | 緩和ガードが `advisory < threshold` しか見ておらず、`AUDIT_GATE_THRESHOLD` で上げた閾値を advisory が上書きしていた（docstring が防止を明記していたにもかかわらず） | `strict_guard` 条件を追加。`ENABLE_AUDIT_ADVISORY_STRICT_GUARD`（既定 ON）で無効化可 | `src/agents/audit_agent.py` |
| 欠測次元がスコアを水増し | repository 無しで factual が unavailable のとき `NEUTRAL_SCORE=100` を**重み付き合計に足していた**ため、4 次元 50・factual 欠測で総合が 60.0 になっていた | 欠測次元を分子・分母の両方から除外して再正規化（評価できた次元の重み付き平均）。`BOOK_SCORE_SKIP_UNAVAILABLE_WEIGHT=0` で旧挙動へ戻せる | `src/services/book_score_service.py` |
| 動的カテゴリで `KeyError` | `categorized_facts` が `self.categories` キー plain dict だが、taxonomy engine が既定外カテゴリを返す経路があった | `defaultdict(list)` 化 ＋ `self.categories` に無いカテゴリを出力から除去 | `src/services/compression/layer3_abstraction.py` |
| RRF 融合の結果が非決定的 | `all_ids = set(...)` の反復順が `PYTHONHASHSEED` でProcesses ごとに変わり、同点 `rrf_score` の並び順がぶれていた | 順序付き union（ベクトル順優先）に変更 | `src/services/vector_store/pgvector.py` `_fuse_results` |

### 5.8 伏線の因果DAG化（W5 完了 / 2026-09-30）

`PLAN_W5_CAUSAL_FORESIGHT_12STEPS.md` の 12 ステップを実装済み。
伏線回収の算出根拠を「話数の算術」から「因果DAG＋物語アンカー＋文脈関連度」へ移行した。

| 項目 | 実装内容 | 根拠 |
|:---|:---|:---|
| 旗艦フラグ | `FORESHADOW_CAUSAL_DAG` / `FORESHADOW_ANCHOR_SNAP` / `FORESHADOW_SHORT_HORIZON` / `FORESHADOW_RELEVANCE_INJECTION` / `FORESHADOW_CASCADE_RESCHEDULE` / `FORESHADOW_RELEVANCE_TOP_K`。**すべて既定 OFF**（既存挙動は現状維持） | `src/services/foreshadowing/flags.py` |
| ビート区間の正規化 | 半開区間 `[start, end)` を採用。境界話（10 / 18 / 25 …）は「次のビート」に属する | `src/services/foreshadowing/anchors.py` `beat_for_episode` |
| 物語アンカー | `opening` / `first_trial` / `midpoint`(19) / `crisis` / `climax`(33) / `resolution`(39) を phase 列から機械的に解決 | `src/services/foreshadowing/anchors.py` `anchor_episode` |
| 短期ホライズン | `SHORT_TERM_HORIZON`（=3）が死んでいたのを実装。`planted + 3` 以内に丸める（不変条件ガードの後段） | `src/services/foreshadowing/planner.py` `use_short_term_horizon` |
| アンカー吸着 | 長期伏線を `min(midpoint, climax)` へ吸着（**前倒しはしない** = `max`） | `planner.py` `anchor_snap` / `LONG_TERM_ANCHOR_ORDER` |
| 因果DAG | 決定論的な依存推定（後続語の正規表現）＋ frozen dataclass。**LLM は呼ばない** | `src/services/foreshadowing/causal_dag.py` |
| 位相順序・依存伝播 | Kahn 法（非再帰）。閉路があっても全IDをちょうど1回返す。`dependents_of` は推移閉包 | 同上 `topological_order` / `dependents_of` / `roots_of` |
| 連鎖延期 | 延期時に依存伏線も一緒に延期（`MAX_CASCADE=10`、CAS 拒否は握り潰す） | `rescheduler.py` `cascade_reschedule` |
| CAS 理由の可視化 | `last_rejection` に `id` / `target_status` / `reason` / `op` を保存 | `src/infrastructure/repositories/foreshadowing_repo.py` |
| 関連度スコアリング | `0.7*cos + 0.3*decay`、期限超過は優先カテゴリへ底上げ。**Embedding API を既定で呼ばない**（Jaccard フォールバック） | `src/services/foreshadowing/relevance.py` |
| プロンプト注入 | `FORESHADOW_RELEVANCE_INJECTION=1` のとき関連度上位 `TOP_K` 件に絞る。**契約鉤子には触らない** | `src/agents/prompt_composer.py` `_load_unresolved_foreshadowings` |
| 終端集中の緩和 | 背景伏線のソートキーに「回収予定が近い順」を追加（上限 20 は据え置き）、省略サマリに「直近の回収推奨: 第N話」を付与 | `prompts/manager.py` `_select_background_foreshadowings` / `FORESHADOW_BUNDLE_LIMIT=5` |

ロールバックは環境変数 1 つで可能（全て既定 OFF に戻すだけ。コード削除不要）。

### 5.9 最適化計画書の索引

| 計画 | 状態 | 主題 |
|:---|:---|:---|
| `plans/PLAN_V6_COST_LATENCY_OPTIMIZATION.md` | 完了 | v6.0.0 のコスト・レイテンシ最適化（親計画） |
| `plans/PLAN_W4_SURGICAL_PATCH_12STEPS.md` | **完了** | 全滅バックトラック → 外科的スパンリライト（12 ステップ） |
| `plans/PLAN_W5_CAUSAL_FORESIGHT_12STEPS.md` | **完了** | 因果的先見（12 ステップ） |
| `plans/PLAN_W6_PREFETCH_CANCELLATION_12STEPS.md` | **完了** | 投機的プリフェッチの効率化＋即時キャンセル（12 ステップ） |

---

## 6. このドキュメントの運用

- 機能を「実装済み」と書くのは、**API 経路が存在し、ディレクトリに配線されている**ことを確認できた場合に限る。未接続のクラスは「未配線」扱いとする。
- 外部ネットワーク・外部サービス・資格情報を要する機能は、コードの記述で判断できる部分だけを記載し、実疎通は **未確認** と明記する。
- 歴史文書（ルートの `*_SUMMARY*.md`、`plans/*.md`）は本ドキュメントより優先度が低い。`plans/` の A1〜A4「96 ステップ」文書は**設計文書**であり進捗の SSOT ではない。

---

## 7. STORY_SPINE 導入の効果測定

構造テンプレート層（`config/story_spine/`）の導入前後の実測値。
**すべて `scripts/measure_spine_alignment.py` の出力。推測値は記入していない。**

| # | 指標 | 現状 | 目標 | 実測値 | 出典 |
|:---|:---|:---|:---|:---|:---|
| K1 | 構成充足度（生成後 `structure_validator` スコア） | 計測不能 | 全書籍で算出可能 | 合成書籍: 0.80 以上（忠実書籍）/ 0.90 未満（崩壊書籍） | `tests/unit/story_spine/test_spine_alignment_measure.py` |
| K2 | 中点反転の相対位置が 0.40〜0.60 に収まる率 | 未知 | 90% | 合成書籍: 100% | `tests/unit/story_spine/test_spine_alignment_measure.py` |
| K3 | クライマックス位置が 0.75〜0.92 に収まる率 | 未知 | 90% | 合成書籍: 100% | `tests/unit/story_spine/test_spine_alignment_measure.py` |
| K4 | テンプレート展開の LLM 追加コスト | — | 0 円 | 0 円（`resolve_spine` は LLM を呼ばない） | `tests/unit/story_spine/test_resolver_no_llm.py`（**5件**緑） |
| K5 | 100話構成が完走する | 不可（`le=40` で弾かれる） | 可能 | 可能 | `tests/regression/test_relative_episode_structure.py`（18件緑） |
| K6 | 1話短編に構造が入る話数 | 0 | 100% | 100%（38パターン全て） | `tests/unit/story_spine/test_resolver_compression.py` |
| K7 | genre→preset 解決率 | `"fan"` が `None` | 100% | 100%（旧4系統の値全て解決） | `tests/regression/test_genre_resolution_unified.py`（26件緑） |
| K8 | `/api/config/planning_options` 応答 | HTTP 500 | 200 | 200 | `tests/contract/test_planning_options_endpoint.py`（7件緑） |

### K1〜K3 の実測値について

`measure_spine_alignment.py` は **DB 内の既存書籍**（`Plot` テーブル）を対象に実測するが、
現在の作業環境に対象書籍が 1 件も存在しない（`book_count = 0`）。
そのため K1〜K3 の **実書籍実測値は `null`** のままとし、合成書籍フィクスチャによる
回帰テスト（`tests/unit/story_spine/test_spine_alignment_measure.py`）で代替計測している。
書籍データが入った環境で `scripts/measure_spine_alignment.py --json` を再実行し、
実書籍の値を差し替えること。

再実行:
```powershell
C:\Python314\python.exe scripts\measure_spine_alignment.py --json
```

### 執筆パイプラインへの配線経路（本計画 H2-H5 で完結）

- `prompts/manager.py` `build_drafting_prompt`（drafting 経路）
- `prompts/manager.py` `build_macro_plot_skeleton_prompt`（macro 骨子生成経路）
- `prompts/manager.py` `build_micro_scene_expander_prompt`（micro 詳細演出経路）
- `src/engine/default_plot_expander.py`（spine 解決フック・fail-open）
- `src/backend/routers/easy_mode.py`（既存、B8）

**最重要契約（off 差分ゼロ）**は全経路で保証済み：
- `tests/contract/test_spine_prompt_injection_drafting.py`（5件緑）
- `tests/contract/test_spine_prompt_injection_plotelements.py`（4件緑）
- `tests/e2e/test_spine_end_to_end.py::test_off_quality_produces_byte_identical_prompt`
- `tests/contract/test_spine_prompt_injection.py`（GraphRAG テンプレ経路、既存）

### 導入の単位

- データ層: `config/story_spine/`（34ビート / 38パターン / 6長さ / 4媒体 / 24カード）
- 解決エンジン: `src/services/spine_resolver.py`（LLM 0回・決定論・全2,736組合せで例外0）
- 検証: `src/services/structure_validator.py`（`pattern_key` 対応。既存3構造は非破壊）
- 段階適用: `SPINE_QUALITY` 環境変数（`off`（既定）/ `soft` / `hard`）
  **`off` では生成プロンプトがバイト単位で従来と同一**であることを
  `tests/e2e/test_spine_end_to_end.py::test_off_quality_produces_byte_identical_prompt` が保証する。

---

### 8. RAG 検索パイプライン baseline（Plan R5 実装前）

| 項目 | 現状（baseline） | 根拠 |
|:---|:---|:---|
| `RAG_CONTEXT_INJECTION`（執筆プロンプト注入） | **未実装／OFF**。`context_builder_agent.py` が組み立てる `rag_context` / `compressed_context` は `prompt_composer.compose_writing_prompt` で消費されず、執筆プロンプトに届かない（dead-letter） | `src/agents/context_builder_agent.py:347-474` / `src/agents/prompt_composer.py:115-136` |
| 検索戦略 | **dense（ベクトル）単一**。`ReflectiveRAGService` は `hybrid_retriever=None` で生成。BM25/RRF（`compute_rrf_scores` k=60）は定義のみで未接続 | `src/backend/tasks/generation_tasks.py:186` / `src/integrations/rag/reflective_rag.py:465-472` |
| HyDE | **LLM 不使用の固定テンプレート**。擬似文書ではなく規則ベース文面 | `src/integrations/rag/query_reformulator.py:77-96` |
| リランカー | **`none`**（Noop）。既定モデル `cross-encoder/ms-marco-MiniLM-L-6-v2` は英語専用で日本語小説に不適 | `src/infrastructure/config/settings.py:309-310` / `src/integrations/rag/reranker.py:97-104` |
| エピソード検索クエリ | `f"{character_name} ep{N}"` の貧弱キーワード | `src/integrations/rag/rag_service.py:872-875` |
| Prometheus メトリクス | RAG 専用メトリクス無し（既存 `reflective_rag_*` のみ） | `src/backend/observability/metrics.py:500-523` |
| 契約（off 差分ゼロ） | 現時点では RAG 関連の contract テスト無し | `tests/contract/` 参照 |

**Plan R5 目標**: 上記をすべて実装・接続し、**フラグ全 OFF では執筆プロンプトがバイト単位で変わらない**（`tests/contract/test_rag_prompt_injection.py` で保証）。フラグ ON 後は提案9の評価基盤で `character_consistency` の人手相関・コスト・レイテンシを before/after 測定する。

---

### 9. 物語構造制御の本番配線（Plan S1 実装・2026-11-10）

精査レポート改善提案 #7 の実装。計画書: `plans/PLAN_S1_STRUCTURE_CONTROL_WIRING_27STEPS.md`。

#### 9.1 配線済みの構造制御経路

| 経路 | 実装 | 既定挙動 | SSOT |
|:---|:---|:---|:---|
| マクロ骨子 構造ゲート | `src/engine/structure_gate.py` `NarrativeStructureGate` → `expand_macro_skeletons` に hook（`src/engine/default_plot_expander.py`） | **off（何もしない / ゲート生成すらしない）** | `config/narrative_structure.yaml` + env `NARRATIVE_STRUCTURE_GATE` |
| micro 展開 tension 差分指示 | `expand_single_micro` 内で直前話 tension との差分を検査し、warn 以上で補正指示 1 行を追記 | off（追記なし・バイト同一） | 同上 |
| プリセット tension curve | `pipeline_steps.py` PlanStep → `get_tension_curve(preset)` → マクロプロンプトへ「参考曲線」注入（O2）＋ ゲート逸脱指標（O3・advisory） | preset 未選択時は None 通し（内蔵既定曲線は出さない） | `src/presets/*/tension/` |
| 伏線回収 LLM 第 4 投票 | `src/engine/foreshadowing/llm_voter.py`（マスキング・temp 0.2・±500字窓 ≤3000字）→ `ForeshadowingService(llm_voter=...)` | **off（LLM 0 回・現行配点 35/40/25 を完全維持）** | `config/audit_calibration.yaml` `foreshadowing:` + env `ENABLE_FORESHADOW_LLM_VOTE`（off/shadow/mainline） |
| CLI balance | `src/cli/main.py` → 各パッケージ CLI（dsp/csp/grammar）へ委譲。ghost import を解消 | 常時有効 | — |

#### 9.2 段階解禁ゲート（R1 — 全て満たさないと次の段階へ進まない）

| 段階 | 内容 | 解禁ゲート |
|:---|:---|:---|
| ① | spine `soft`（新規書籍のみ） | F1B の K1-K3 合成書籍実測維持 ＋ `tests/contract/test_spine_prompt_injection_*.py` 全緑 |
| ② | gate `warn`（全書籍・副作用ゼロ） | ① の継続 ＋ `NARRATIVE_STRUCTURE_GATE=warn` で 1 作品（40話）生成し **テンション違反率 ≤ 10% を実測記録** |
| ③ | gate `enforce`（新規書籍のみ・tension のみ補正） | ② の実測 ＋ `tests/contract/test_structure_gate_off_contract.py` 全緑 ＋ 補正後残余違反が実測で減少 |
| ④ | 伏線投票 `mainline`（SSOT 配点 35/30/20/15） | `ENABLE_FORESHADOW_LLM_VOTE=shadow` の記録で **一致率 ≥ 0.70** ＋ metadata 過大申告率が有意（`python -m scripts.analyze_foreshadow_vote_agreement`）。**過大申告が無ければ mainline 化は見送り** |

#### 9.3 回帰テスト（全て LLM 0 回・インメモリ/モック）

- `tests/contract/test_structure_gate_off_contract.py` — off で挙動バイト同一・fail-open
- `tests/contract/test_tension_curve_injection.py` — curve None でバイト同一・spine 優先
- `tests/unit/narrative_balancer/test_structure_gate_wiring.py` / `test_structure_gate_failopen.py` — 換算・決定論・LLM 0 回・fail-open
- `tests/unit/engine/test_structure_gate_macro_hook.py` / `test_micro_tension_delta.py` — 配線順序・補正指示
- `tests/config/test_narrative_structure_setting.py` — SSOT 契約・ハードコード再導入防止（AST）
- `tests/unit/engine/foreshadowing/`（`test_llm_voter.py` / `test_ensemble_four_votes.py` / `test_vote_shadow_recording.py`）— fail-open・マスキング・legacy 判定同一性・shadow 記録
- `tests/unit/narrative_balancer/test_cli_balance_imports.py` — CLI 委譲契約

#### 9.4 既知の残作業

- ~~F1B H7（Studio/wizard への per-book spine 選択 UI）~~ → **2026-11-10 完装**。
  `SimpleModePanel` に 3 択セレクタ（既定 off・「テンプレートは初期値」注記付き）。
  `NovelContext.spineQuality` → `useNovelGeneration` / `useStreamingWriter` の payload
  （off は送信しない）→ `EasyModeInput.spine_quality` → `execute_generation` で消費。
  バックエンドの `None` は env 既定 `SPINE_QUALITY` に倒れる（従来互換）。
- R1-②/③/④ の実測は運用（1 作品分の shadow/warn 生成）が必要

---

### 10. 改稿（パッチ / 教訓）baseline（Plan H8 実装前）

| 項目 | 現状（baseline） | 根拠 |
|:---|:---|:---|
| 改稿パッチ方式 | `UnifiedAuditor.actionable_patch` は**本文末尾へ追記**（`drafted_text + "\n\n" + actionable_patch`）。置換ではないため文脈矛盾が残留しうる | `src/agents/audit_agent/agent.py:704-722` / `src/backend/workflows/writing_langgraph.py:585-600`（デッドパス） |
| ProseRefinerAgent fail-open | LLM 未設定時に `response = prompt` — **プロンプト文字列自体が本文に混入する** | `src/agents/writing/prose_refiner_agent.py:167-168` |
| actionable_patch schema | 単一文字列のみ。置換対象 `original_quote` は非要求（`improved_suggestion` と `original_quote` を持つ `ActionableDiff` は 8専門家のみ） | `src/models/unified_audit.py:25` / `src/agents/prompts/unified_audit_prompt.py:31` |
| 監査失敗教訓 | **話横断で永続化されない**。`failed_audits` は artifacts 内で 1 話のみ。同一失敗が次話以降で再発する | `src/agents/audit_agent/agent.py:1058-1132` |
| 設定フラグ | 無し（`ENABLE_AUDIT_QUOTE_PATCH` / `ENABLE_AUDIT_LESSONS` 未定義） | `src/agents/audit_agent/config.py` grep 確認 |
| Prometheus メトリクス | 改稿・教訓専用メトリクス無し | `src/backend/observability/metrics.py` grep 確認 |
| 契約（off 差分ゼロ） | H8 関連の contract テスト無し | `tests/contract/` 参照 |

**Plan H8 目標**: `quote_patch`（`original_quote` 必須の検証付き置換）と `audit_lessons`（話横断教訓メモリ）を追加。**フラグ全 OFF では改稿・教訓経路の挙動をバイト単位で変えない**（`tests/contract/test_h8_quote_patch_contract.py` / `test_h8_lessons_prompt_injection.py` で保証）。フラグ ON 後は提案9の評価基盤でパッチ採用率・再合格率・同 dimension 再発率を before/after 測定する。

---

### 11. H8 フラグ AB 検証結果と既定値判定（PLAN_H8F O7-O9 実施・2026-11-11）

合成データセット（3 プリセット × 20 話 = 60 話、structured diff 98 件うち不良差分 20 件、`var/ab_datasets/h8/`・コミット対象外）を用い、`try_local_patch` / `AuditLessonService` の実コード経路で LLM なしの決定論的 AB を実施した。

#### quote_patch AB（D1）

| ケース型 | 条件 A (flag=0 追記互換) | 条件 B (flag=1 quote_patch) | 差 |
|:---|:---|:---|:---|
| whitespace-shift（LLM が半角空白で quote、n=60） | 戦略 none・解決率 **0%** | 戦略 quote_patch 52/60・解決率 **87%** | **+87%** |
| legacy-only（legacy 文字列のみ、n=60） | 戦略 actionable_patch 60・解決率 0% | 戦略 quote_patch_legacy 60・解決率 0% | ±0% |
| 段落破壊 | 0 件 | **0 件**（SpanPatchApplier 保証の実測） | — |

採用率: 52/(52+8) = **87%**（基準 ≥60% を達成）。ただし**再合格率とコスト増は実 LLM 生成 AB が必要なため未測定** → 判定条件を満たさず。

知見: whitespace-shift ケース（SafeReplacer 逐語一致が不発するケース）で quote_patch が解決率 0%→87% に改善。legacy 文字列のみでは TargetedDiagnostic が指摘対象段落を特定できず解決率 0% — structured `original_quote` 必須化（H8 Phase C）の設計判断を実測で裏付け。

#### lessons AB（D2/D3）

| 指標 | 条件 B (`MIN_OCCURRENCES=1`) | 条件 C (`=2`) |
|:---|:---|:---|
| 注入件数 | 5 | 3 |
| ノイズ（ワンオフ一時的失敗の混入） | 2 件 | **0 件** |
| 反復 dimension カバレッジ | 100% | 100% |
| 注入ブロック文字数（上限 800） | 195 字 | 124 字 |

メカニズム実測: 14 失敗イベント → 4 教訓に重複統合（occurrences 分布 {7:1, 3:1, 2:2}）、`AUDIT_LESSON_ACTIVE_MAX` エビクション動作（active=10 上限・archived=6）、fail-open（session 未取得 / DB 破損で監査フロー継続）確認。ただし**再発率低下は実 LLM 生成 AB が必要なため未測定** → 判定条件を満たさず。

#### 判定（PLAN_H8F O9）

| 決定 | 判定 | 根拠 |
|:---|:---|:---|
| `ENABLE_AUDIT_QUOTE_PATCH` | **既定 OFF 維持** | 採用率 87%・破壊 0 と部分証拠は良好だが、再合格率・コストが未測定。実パイプライン AB 後に再判定 |
| `ENABLE_AUDIT_LESSONS` | **既定 OFF 維持** | メカニズム動作確認済みだが、再発率低下が未測定。同上 |
| `AUDIT_LESSON_MIN_OCCURRENCES` | **既定 1 → 2 に変更** | カバレッジ 100% 維持のままワンオフノイズ 2 件 → 0 件（O8 実測） |

**再判定条件**: 実パイプライン（実 LLM）で PLAN_H8F O7/O8 の手順を 3 プリセット × 20 話で再実行し、O9 の判定表を全項目埋めた時点で再判定する。ロールバックは flag 1 本（`ENABLE_AUDIT_QUOTE_PATCH=0` / `ENABLE_AUDIT_LESSONS=0`）で旧挙動に戻る（`tests/contract/test_v6_audit_surgical_patch.py` フラグマトリクスで常時検証）。

**運用上の修正**（本判定に伴う実装）: `record_audit_revision` / `record_audit_lesson` / `record_audit_lessons_injected` をパイプラインに配線（AB 計測に必須）、`AUDIT_LESSON_ACTIVE_MAX` を `lesson_store._enforce_active_max` に接続（エビクションが環境変数に従うよう修正）、`0035_audit_lessons` の分岐を解消（`down_revision=0035_digest_rollups`、複数 head による `alembic upgrade head` 失敗の修正）。
