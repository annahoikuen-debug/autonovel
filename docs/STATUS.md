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
- **未達の原因**: 1話の 10 回のうち 5 回（50%）が監査フェーズである。
  ゲート集約（Step 23）で再執筆は減ったが、**監査の LLM 呼出回数自体は減っていない**。
  回数を減らすには監査数の削減（軽量監査モード）が必要で、本計画の範囲外。

### 5.2 監査レイテンシ（並列化 Step 21 の効果）

| 指標 | 目標 | 実測 | 判定 |
|:---|:---|:---|:---|
| 直列 | — | **0.144 ms**（中央値, 5回） | — |
| 並列 | 約 1/5 | **0.300 ms**（中央値, 5回） | **未達（短縮率 0.48倍）** |

- 出典: `tests/perf/test_v6_audit_latency_and_regen.py::test_audit_latency_measured_parallel_vs_serial`
- **測定条件**: 決定的なスタブ LLM = **I/O 待ちが無い**。この条件では
  `asyncio.gather` のオーバーヘッドが相対的に支配的になり、短縮にならないのが正常。
- **重要**: 本番のように**ネットワーク I/O が支配的な**場合の短縮率は
  **未計測**（実 API を叩く必要があるため）。本表の数値で効果を断定してはならない。

### 5.3 本文再生成比率（ゲート集約 Step 23 の効果）

| シナリオ | 再生成比率 | aggregate_score | gate mode |
|:---|:---|:---|:---|
| 全5監査が不合格（最悪ケース） | **100%** | 39.23 | `score_aggregation` |
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
| 弱段落の特定 | `TargetedDiagnostic` の TODO スタブを実装（`ClosedLoopPDCARunner` の段落パッチ経路が到達可能に） | `src/services/audit/targeted_diagnostic.py` |
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
| K1 | 構成充足度（生成後 `structure_validator` スコア） | 計測不能 | 全書籍で算出可能 | `null`（対象書籍0件） | `measure_spine_alignment.py --json` |
| K2 | 中点反転の相対位置が 0.40〜0.60 に収まる率 | 未知 | 90% | `null`（対象書籍0件） | 同上 |
| K3 | クライマックス位置が 0.75〜0.92 に収まる率 | 未知 | 90% | `null`（対象書籍0件） | 同上 |
| K4 | テンプレート展開の LLM 追加コスト | — | 0 円 | 0 円（`resolve_spine` は LLM を呼ばない） | `tests/unit/story_spine/test_resolver_no_llm.py`（7件緑） |
| K5 | 100話構成が完走する | 不可（`le=40` で弾かれる） | 可能 | 可能 | `tests/regression/test_relative_episode_structure.py`（18件緑） |
| K6 | 1話短編に構造が入る話数 | 0 | 100% | 100%（38パターン全て） | `tests/unit/story_spine/test_resolver_compression.py` |
| K7 | genre→preset 解決率 | `"fan"` が `None` | 100% | 100%（旧4系統の値全て解決） | `tests/regression/test_genre_resolution_unified.py`（26件緑） |
| K8 | `/api/config/planning_options` 応答 | HTTP 500 | 200 | 200 | `tests/contract/test_planning_options_endpoint.py`（7件緑） |

### K1〜K3 が `null` である理由

`measure_spine_alignment.py` は **DB 内の既存書籍**（`Plot` テーブル）を対象に実測するが、
現在の作業環境に対象書籍が 1 件も存在しない（`book_count = 0`）。
**空の測定結果を捏造しない**ため `null` のまま記載する。
書籍データが入った環境で再実行し、値を差し替えること。

再実行:
```powershell
C:\Python314\python.exe scripts\measure_spine_alignment.py --json
```

### 導入の単位

- データ層: `config/story_spine/`（34ビート / 38パターン / 6長さ / 4媒体 / 24カード）
- 解決エンジン: `src/services/spine_resolver.py`（LLM 0回・決定論・全2,736組合せで例外0）
- 検証: `src/services/structure_validator.py`（`pattern_key` 対応。既存3構造は非破壊）
- 段階適用: `SPINE_QUALITY` 環境変数（`off`（既定）/ `soft` / `hard`）
  **`off` では生成プロンプトがバイト単位で従来と同一**であることを
  `tests/e2e/test_spine_end_to_end.py::test_off_quality_produces_byte_identical_prompt` が保証する。