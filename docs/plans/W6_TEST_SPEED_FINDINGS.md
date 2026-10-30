# W6 テストスイート速度改善 — 調査記録と既知課題

実施日: 2026-10-30（Fri）
ブランチ: main（未コミット作業ツリー上）

## 1. 方針（ユーザー確認済み）

- **テスト側のみ修正**：「RAM不足時に run_dag が無限ループする」製品側の livelock は**製品挙動は変更せず**、課題として記録のみ。
- **ハング修正＋収集30秒以内**：tests/unit が完走し、収集（`pytest --collect-only -q | tail`）が30秒以内（pytest自己申告値）を回帰ゲートとする。

## 2. 根因：3件の無限ハング（すべて >45s で強制終了）

| テスト | 根因 | 種別 | 修正内容 |
|---|---|---|---|
| `tests/unit/backend/test_backend_tasks_dag_stack.py::test_acquire_resources_rolls_back_on_cancel` | 初回取得を解放せず2回目を呼ぶ＋アサートが恒真式 (`a == a`)。`ram_slots=1` の環境で2回目が永久ブロック。 | テストバグ | セマフォ容量を固定（cpu/ram=4, gpu=1）、取得→解放の順序を明示、ロールバックで cpu/ram の元値復帰をアサート |
| `tests/unit/test_dag_scheduler.py::test_build_novel_generation_dag_pipeline` | 空きRAM 594MB → `ram_slots=1`。ノード `b1_ep1_write` は `ram_mb=1024`（必要2スロット）→ `can_schedule_approx=False` のまま `run_dag` が `launched==0` の永久ポーリング（`select()` ブロック）。 | 環境依存の製品livelock | `tests/helpers/dag_resources.py::patch_available_ram()` で `ResourceManager.get_available_ram_mb` を固定（16384MB） |
| `tests/unit/test_dag_scheduler_part5_advanced.py::test_run_novel_dag_pipeline_async` | 同上。内部で `DAGScheduler()` を生成するため、クラスメソッド差し替えで全経路に効かせる。 | 環境依存の製品livelock | 同上 |

### 根拠（実測）

```
マシン RAM: total 2772MB / available 594MB
max_ram_ratio 0.8 → ram_slots = 594×0.8//512 = 1
b1_ep1_write  ram_mb=1024 → ram_slots必要=2 → can_schedule=False
→ run_dag 10秒後も未完了、semaphores cpu=2 ram=1 gpu=1（全て充足！）、
  ノード状態 plot=completed, context=completed, write=ready（発行されず）
```

仮修正（RAM 固定）検証：`run_dag` が **0.00s で 6ノード全ノード完了 / failures=False** を実証済み（`tests/helpers/dag_resources.py` を使うとどのマシンでも緑・高速）。

## 3. 遅いだけで合格の4件（ハングではない）

| テスト | 実測 | 原因 |
|---|---|---|
| `test_publish_network_error` | 16.55s | `NarouPublisher.publish` の `@async_retry(max_attempts=3, base_delay=5.0)` → NetworkError のバックオフ遅延 |
| `test_update_chapter_rate_limit_and_network` | 16.63s | 同上（`@async_retry` 遅延） |
| `test_scheduler_cancels_running_tasks_on_failure` | 21.27s | テスト本体で `await asyncio.sleep(10.0)` |
| `test_taskgroup_cancels_on_fatal_failure` | 21.47s | テスト本体で `await asyncio.sleep(10.0)` |

これらは遅延を意図したテストであり、計上対象外（合格）。

## 4. 収集時間（`pytest --collect-only -q | tail`）

| 段階 | 実測（2026-10-30） |
|---|---|
| configure（`conftest.pytest_configure` → `import src.backend.server`） | 13.2〜15.2s |
| collection（9507件、pytest自己申告） | 17.3〜23.7s（測定例 19.83s） |
| wall 合計 | 31.4〜46.8s（揺らぎ大） |

**wall ≤30s はテスト側では達成不能**：`src.backend.server` は **35個のテストモジュール**が module 直下で import しており、configure の import を外しても collection が同コストを吸収（ネットゼロ）。また dependency_injector の `containers.py` が Container 定義時に `inspect.stack()` を発火するため起動が重い。

回帰ゲートとしては **pytest自己申告値（`tail` が出す秒数）** を採用（`tests/regression/test_collection_health_gate.py::TestCollectionSpeed::test_collection_seconds_within_budget`）。wall は参考値として上限180秒で異常のみ検出。

## 5. 既知の失敗（W6 の範囲外・環境起因・既存）

`tests/unit` 完走後（341s / 7505 passed）の残存：65 failed / 36 errors。主なもの:

- 36 errors: `test_auth_middleware`（AUTH_DISABLED バイパス）、`test_database_core`（DB wrapper 引数不一致）、sqlite `:memory:` URL エンコード
- missing deps: `ebooklib` / `rank_bm25` / `chromadb` / `google.genai` 等未導入

これらは「W6で回帰を導入していない」こと（HEADからの変化なし）を確認済み。

## 6. 製品側 livelock（未修正・記録のみ）

`src/backend/tasks/dag_scheduler.py::_acquire_resources` / `run_dag` は、要求RAMが空き容量を超えるノードを「発行せず永久ポーリング」する。正常なマシンでは ram_slots が大きく表面化しないが、メモリ制約環境（CI含む）ではゾンビ化する。

**対応方針（本PR）**: テスト側でRAM固定して回避。製品側の fail-fast / ライブロック検出は別課題（TRACK-Q または architecture 改善の課題）として保留。

## 7. 変更ファイル（W6）

- `tests/unit/backend/test_backend_tasks_dag_stack.py` — `test_acquire_resources_rolls_back_on_cancel` をロールバック検証に変更（ハング除去）
- `tests/unit/test_dag_scheduler.py` — `test_build_novel_generation_dag_pipeline` に `patch_available_ram(monkeypatch)` を追加
- `tests/unit/test_dag_scheduler_part5_advanced.py` — `test_run_novel_dag_pipeline_async` に `patch_available_ram(monkeypatch)` を追加
- `tests/helpers/dag_resources.py` (新規) — `patch_available_ram()` リソース固定ヘルパ
- `tests/regression/test_collection_health_gate.py` — 収集速度回帰ゲート `TestCollectionSpeed` 追加（30秒予算＋1000件以上＋1回実行のメモ化）

ruff: 全ファイル緑（dag_stack の F841 `reset = g and None` のみ HEAD 既存）。

## 8. 検証結果

| 項目 | 修正前 | 修正後 |
|---|---|---|
| 3件ハングテスト | 45s超で強制終了 | 0.31〜0.82s で **passed** |
| `tests/unit/backend/test_backend_tasks_dag_stack.py` 全体 | （ハングで完走不可） | 68 passed, 1 skipped |
| `tests/unit/test_dag_scheduler.py` 全体 | （ハングで完走不可） | 8 passed in 42.85s |
| `tests/unit/test_dag_scheduler_part5_advanced.py` 全体 | （ハングで完走不可） | 6 passed in 1.01s |
| `tests/unit` 全体 | 3時間超・完走不可 | 341s / 7505 passed（完走） |
| `pytest --collect-only` | 17.3〜23.7s（自己申告） | 19.83s（変更なし＝回帰なし） |
| 収集ゲート（新設） | — | 3 passed in 35.71s |

## 9. 継続課題（TRACK-Q / TRACK-A 以降）

- 製品側 `run_dag` ライブロックの fail-fast 化（要求RAM超過を明示エラー）
- `tests/unit` の 65 failed / 36 errors（環境・未導入deps）の整理
- 収集 time wall ≤30s（conftest / server import の高速化は次ステップ）
