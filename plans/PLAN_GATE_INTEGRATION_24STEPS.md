# 統合テスト 9件の緑化と CI ゲート化 実装計画（全24ステップ）

- **作成日**: 2026-11-08
- **対象ブランチ**: `feature/commercial-lp-phase1`（基準コミット `4aa42338`）
- **ゴール**: `tests/integration` の失敗9件をゼロにし、`.github/workflows/ci.yml` の
  `integration-observe` を `continue-on-error: false` に切り替えて**本物のゲート**にする。
  9件をゼロにできない場合は「未達」と明記し、**「観測」という言い換えを禁止**する。

---

## 0. 絶対条件（全ステップ共通）

### 0.1 リグレッション防止の3原則

1. **テスト期待は緩和しない。** 実装がバグなら実装を直す。
   「テストの期待値を実装に合わせる」は本計画では**禁止**（厳格評価で指摘済みの
   検知力低下を繰り返さないため）。例外は Step 16 のみで、正当性を証明できる場合のみ許可。
2. **各ステップは「修正 + リグレッション防止テスト + 全緑確認」で完結**する。
   修正だけのステップは存在しない。
3. **1ステップ = 1コミット**。コミットメッセージに「修正前 failed 数 → 修正後 failed 数」を書く。

### 0.2 検証コマンド（全ステップ共通）

```bash
# 統合（基準: 9 failed / 336 passed / 37 skipped, 約75〜95秒）
.venv/bin/python3 -m pytest tests/integration -q --timeout=180 -p no:cacheprovider \
  -W ignore::DeprecationWarning

# 単体（基準: 8075 passed）
.venv/bin/python3 -m pytest tests/unit -q -p no:cacheprovider

# 回帰（基準: 620 passed / 8件は既知失敗）
.venv/bin/python3 -m pytest tests/regression -q -p no:cacheprovider

# 収集エラーの有無（SyntaxError 混入の検出）
.venv/bin/python3 -m pytest tests/integration --collect-only -q -p no:cacheprovider
```

**判定基準**: どのステップでも「統合 failed 数が前ステップ以下」かつ
「単体・回帰の passed 数が前ステップ以下でないこと」を満たすこと。

### 0.3 並行セッションとの競合回避（重要）

本作業開始時点の調査で、**同一作業ディレクトリで別セッションが同時作業中**であることが確認された。

| 時刻 | 起きたこと |
|---|---|
| 06:12〜06:18 | 別セッションが52ファイルへ型アノテーションを自動付与 |
| 06:16:35 | その過程で `src/infrastructure/repositories/foreshadowing_repo.py:383` に **SyntaxError** を混入（`stmt = (` の内側に `stmt: Select[Any] = (` が入れ子になった壊れた編集） |
| 06:18頃 | 別セッションが `git stash` で52件を退避 → `stash@{0}` に保存済み |
| 06:16〜 | 未追跡ディレクトリ `src/agents/audit_agent/` を新設（`audit_agent.py` 1439行の分割作業と見られる） |

**本計画の遵守事項**:

- `stash@{0}` と `src/agents/audit_agent/` は**別セッションの所有物**。本計画では一切触らない。
- 作業開始前に毎回 `git status --short` と `git stash list` を確認し、
  自分が作っていない変更が増えていたら**作業を止めてユーザーに報告**する。
- `plans/` 以外のファイルを編集するステップ（Step 4, 9, 10, 13, 15, 18, 19, 22）は、
  編集対象ファイルが別セッションの編集対象と重ならないことを**編集前に必ず確認**する。
- SyntaxError 混入の再発防止として、**全ステップの完了条件に `--collect-only` 成功を含める**。

### 0.4 ローカルと CI の環境差（ゲート化の最大リスク）

| 項目 | ローカル | CI |
|---|---|---|
| DB | SQLite（`real_db_manager` が `DATABASE_URL` を一時ファイルに差し替え） | PostgreSQL（`pgvector/pgvector:pg16` サービス） |
| Redis | なし | `redis:7-alpine` |
| `AUTH_DISABLED` | 未設定 | `"true"` |
| `AUTONOVEL_RAG_MODE` | 未設定 | `memory` |
| `RAG_FALLBACK_MODE` | 未設定 | `memory` |

**ローカルで緑でも CI で赤になり得る。** したがって Step 21 でゲート化の前に
**CI 上での全件緑を実測**しない限り、`continue-on-error: false` へ切り替えない。

---

## 1. 失敗9件の根本原因（調査完了・実測済み）

基準: `4aa42338` で `pytest tests/integration` を3回実行し、**毎回同じ9件**が失敗することを確認。

### グループ A: `test_async_generation`（2件）— **実装バグ**

```
E AssertionError: assert 'pending' == 'completed'          (line 124)
E assert None is not None                                  (line 228)

ERROR generation_tasks.py:427 Failed to deduct credits for book_id 999:
     object CursorResult can't be used in 'await' expression
ERROR generation_tasks.py:379 DB update failed for task_id=... status=failed
```

**連鎖の構造**:

1. **バグA**: `src/backend/tasks/generation_tasks.py:415` の
   `_asyncio.run(credit_service.deduct_credits(...))` が、
   **同期 `SessionLocal()` を生成した `CreditService` を `await` している**。
   同期 `Session.execute()` は `CursorResult` を返すので `await` すると
   `TypeError: object CursorResult can't be used in 'await' expression` になる。
   → クレジット控除が失敗する。
2. 失敗ハンドラが `_update_task_in_db(task_id, "failed")` を呼ぶが、
3. **バグB**: それも `generation_tasks.py:379` で失敗してロールバックする。
   → ステータスが更新されず、**最初のまま `pending` のまま残る**。

**なぜ1つ目のテストは通るのか**: `test_generation_task_persists_and_cleans_up` は
`book_id` を payload に含めないため、クレジット控除ブロック（`if book_id is None:` の else 分）
がスキップされ、正常系に到達する。**`book_id` を渡した2つのテストだけが落ちる**という
観測と完全に整合する。

### グループ B: `test_book_score_feedback_loop`（2件）— **実装バグ**

```
E assert 0 >= 2                       (line 92)  ← book_score_calculator.calculate が1回も呼ばれていない
E assert 1 == 4                       (line 131) ← writer.generate_episodes が1回しか呼ばれていない
```

**原因**: `src/generation/pdca_controller.py:13` の既定値 `max_regenerations: int = 0`。
`src/domain/writing/coordinator.py:155` が

```python
if not self.pdca_controller.should_regenerate_full_text():
    ...  # 局所ポリッシュのみ → return word_count
```

と先に抜けるため、**`auto_regenerate=True, max_retries=3` を明示指定しても
再生成ループ（`coordinator.py:167` の `for retry in range(max_retries)`）に一切到達しない**。

→ `writer.generate_episodes` は初回の1回のみ、`book_score_calculator.calculate` は0回。
**呼び出し側の明示指定が無言で無視される**のは実装側の不備と判定する。

### グループ C: `test_audit_aggregator_pipeline`（1件）— **正当性の確認が必要**

```
E assert <AgentName.WRITING: 'writing'> == <AgentName.ILLUSTRATION: 'illustration'>
```

**原因**: LLM 未設定のため `src/agents/specialists/unified_auditor.py` が
`degraded=True`（「評価そのものが成立していない」）を返し、
品質ゲートが不合格として `ILLUSTRATION` に進めず `WRITING` へ戻す。
コード中のコメント（`unified_auditor.py:31,49`）はこの挙動を**意図的**と明記している。

→ ここは「実装バグか正当か」を **Step 15 で判定する**。
正当と証明できればテスト側の setup（LLM をスタブ化して degraded を回避させる）を直す。
**ただし期待値（`next_agent == ILLUSTRATION`）は緩和しない。**

### グループ D: `test_migrations`（1件）— **環境汚染（順序依存）**

```
sqlite3.OperationalError: table credit_transactions__0033 already exists
```

**単体実行では `4 passed, 1 skipped` で緑**、全体実行でのみ赤（3回実行で毎回再現）。

**原因の連鎖（特定済み）**:

1. `src/backend/alembic/env.py:20`:
   ```python
   database_url = os.environ.get("ALEMBIC_DATABASE_URL", config.get_main_option("sqlalchemy.url"))
   ```
   → **環境変数が `config.set_main_option()` より優先する**。
2. `src/backend/database/core.py:391` がマイグレーション実行の副作用として
   `os.environ["ALEMBIC_DATABASE_URL"] = sync_url` を**プロセス全体に書き込む**。
3. これを行うテストが先に走ると、後続の `test_migrations_up_down` は
   `sqlite_db_url`（`tmp_path` の新規ファイル）ではなく
   **既に移行済みの別DB**に対して `command.upgrade(alembic_cfg, "head")` を実行し、
   `CREATE TABLE credit_transactions__0033` が二重発生して落ちる。

### グループ E: `test_reflective_rag_context_builder`（1件）— **要診断**

```
E assert 0 > 0   where 0 = len([])     (line 104)
```

`writing_context["rag_context"]` が空。
`sample_candidates` の score は 0.95 / 0.92 / 0.88 で全て `relevance_threshold=0.5` を上回るため、
単純な閾値フィルタでは空にならない。`src/agents/context_builder_agent.py:341-367` の
`retrieve_with_reflection` 呼び出しが例外を送出し
`except Exception`（line 366）で握り潰されている可能性が高い。
**Step 17 で実測して原因を確定させる。**

### グループ F: `test_relational_memory_e2e`（2件）— **要診断**

```
E assert 0 == 1   where 0 = len([])     (line 210)  ← check_and_resolve が0件返却
E Failed: DID NOT RAISE Exception       (line 389)  ← 例外が伝播していない
```

- **line 210**: `src/engine/foreshadowing/service.py:67-69` が
  `unresolved = await self.repo.get_unresolved(book_id)` で空なら即 `return []`。
  伏線の「設置」が repo に届いていない、または status フィルタに掛かっていると推定。
- **line 389**: テストは `build_context` が DB 例外を伝播すると期待しているが、
  実装側が `try/except` で握り潰している。**テストのコメントは
  「実装では例外が伝播するため、呼び出し側でtry/exceptが必要」と書いている**のに、
  実装は握り潰している — テストと実装の意図が正面から衝突している。
  **Step 19 でどちらが正しいかを判定する。**

---

## 2. 全24ステップ

> 各ステップの書式: **目的 / 手順 / リグレッション防止テスト / 完了条件**

---

### Phase 0: 基盤と安全弁（Step 1〜3）

#### Step 1 — 現状スナップショットの固定と作業環境の安全確認

**目的**: 以後の全ステップの「基準」を1箇所に固定し、並行セッションとの競合を検知できるようにする。

**手順**:
1. `git status --short` / `git stash list` / `git log --oneline -1` を実行し、
   自分が作っていない変更がないことを確認する。あれば**ここで作業を止めて報告**。
2. 失敗9件のリストをコマンドで取得し、計画書の付録 A に貼り付ける:
   ```bash
   .venv/bin/python3 -m pytest tests/integration -q --timeout=180 -p no:cacheprovider \
     -W ignore::DeprecationWarning 2>&1 | grep "^FAILED" | tee /tmp/opencode/baseline_failed.txt
   ```
3. 付録 A に「基準: 9 failed / 336 passed / 37 skipped」「基準コミット `4aa42338`」を明記。

**リグレッション防止テスト**: このステップ自体にテストはない。
代わりに **Step 2 のラチェット基準ファイル**がこのスナップショットを永続化する。

**完了条件**: 付録 A が9件で埋まっている。`git status` が計画書以外の変更を返さない。

---

#### Step 2 — 失敗数ラチェットの基準ファイルと検出テストを新設 ★

**目的**: 「9件」を**機械が判定できる数値**として固定し、以後どのステップでも
**失敗数が増えると即座に赤くなる**ようにする。これが本計画全体のリグレッション防止の背骨。

**手順**:
1. `config/integration_failure_baseline.json` を新規作成:
   ```json
   {
     "baseline_commit": "4aa42338",
     "max_failed": 9,
     "known_failures": [
       "tests/integration/test_async_generation.py::test_generation_task_saves_to_specified_book_id",
       "tests/integration/test_async_generation.py::test_generation_task_creates_new_book_when_book_id_not_provided",
       "tests/integration/test_audit_aggregator_pipeline.py::test_audit_aggregator_pipeline_integration",
       "tests/integration/test_book_score_feedback_loop.py::test_writing_service_regeneration_loop_success",
       "tests/integration/test_book_score_feedback_loop.py::test_writing_service_regeneration_max_retries",
       "tests/integration/test_migrations.py::test_migrations_up_down",
       "tests/integration/test_reflective_rag_context_builder.py::test_context_builder_with_reflective_rag_success",
       "tests/integration/test_relational_memory_e2e.py::TestRelationalMemoryE2E::test_foreshadowing_lifecycle_plant_to_resolve",
       "tests/integration/test_relational_memory_e2e.py::TestRelationalMemoryE2E::test_error_handling_in_pipeline"
     ],
     "gate_target_failed": 0
   }
   ```
2. `tests/regression/test_gate_integration_ratchet.py` を新規作成（詳細は Step 3 で拡張）。
   まず最小版として、**基準ファイルの構造健全性**だけを検証する:
   - JSON がパースできること
   - `known_failures` が9件で、各行が `tests/` で始まり `::` を含むこと
   - `max_failed >= gate_target_failed` であること
   - `known_failures` に重複がないこと

**リグレッション防止テスト**: 上記の構造健全性テスト（このステップで作る）。
失敗数そのものは Step 23 で CI 上で検証する（ローカルには postgres/redis が無いため）。

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_gate_integration_ratchet.py -q -p no:cacheprovider
# → passed
```

---

#### Step 3 — 「未達」を明記する CI コメントと docs の記述ルール ★

**目的**: ゲート化できない場合に**「観測」と称さず「未達」と明記する**義務を、
**計画の段階で文書化**しておく。後から言い訳ができないようにする。

**手順**:
1. `.github/workflows/ci.yml` の `integration-observe` ジョブ上のコメント
   （L139-144、`# 統合テスト（観測モード）` のヘッダを含む）を書き換える。
   現行文:
   ```
   # tests/integration は現状 54 件の既知失敗（...）と
   # testcontainers 必須テストを含むため、まずは観測モード (continue-on-error) で
   # CI に組み込み、毎回の失敗リストを可視化する。緑化は別計画で段階的に行う。
   # 緑化完了後は continue-on-error: false に切り替えてゲート化すること。
   ```
   → 件数「54 件」は**既に古い**（現在9件）。以下に更新する:
   ```
   # 統合テストのゲート化（本計画: plans/PLAN_GATE_INTEGRATION_24STEPS.md）
   #
   # 現状: 9 failed / 336 passed / 37 skipped（基準コミット 4aa42338）
   # 状態: 未達 —— continue-on-error: true は「観測」ではなく「未達」を意味する。
   #        9件をゼロにするまで false に切り替えない。切り替え条件は Step 21。
   #
   # ★禁止事項: 失敗を「既知失敗」「観測モード」「許容範囲」等と呼び換えて
   #   ゲートを外すこと。未達は未達と書く。
   ```
2. `docs/PLAN_C_SUMMARY.md` の統合テスト進捗セクションに同じ「未達」表記を追記する。
3. **記述ルールを1箇所に集約**する: `docs/TEST_GATE_POLICY.md` を新規作成し、
   - ゲートの状態は `green` / `red` / `未達` の3値のみ
   - `未達` は failed 数 > 0 のあらゆる状態を指す
   - 「観測」「observe」「known failure」といった緩和語の使用を禁止
   - 解除条件: `gate_target_failed = 0` かつ Step 21 の CI 実測が通ること

**リグレッション防止テスト**: `tests/regression/test_gate_policy_docs.py` を作成:
- `docs/TEST_GATE_POLICY.md` に「未達」の定義と禁止語リストが含まれること
- `.github/workflows/ci.yml` に `continue-on-error: true` が残っている間は、
  その直前のコメントに「未達」が書かれていること（文字列検索）
- `docs/PLAN_C_SUMMARY.md` に「54 件の既知失敗」という**古い件数が残っていない**こと

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_gate_policy_docs.py -q -p no:cacheprovider
# → passed
```

---

### Phase 1: 環境汚染と順序依存の解消（Step 4〜7）

> **先にやる理由**: グループ D は「他のテストの副作用で落ちる」型であり、
> これが残っていると**他のステップの緑化結果が汚染され、成否判定が不安定になる**。

#### Step 4 — `test_migrations` の `ALEMBIC_DATABASE_URL` 隔離 ★

**目的**: グループ D（1件）を緑化する。

**手順**:
1. `tests/integration/test_migrations.py` の `test_migrations_up_down` に、
   フィクスチャまたは `monkeypatch` で環境変数を隔離する:
   ```python
   def test_migrations_up_down(sqlite_db_url, monkeypatch) -> str:
       # src/backend/alembic/env.py:20 は ALEMBIC_DATABASE_URL を
       # config.set_main_option() より優先して読む。
       # src/backend/database/core.py:391 がプロセス全体に書き込むため、
       # 他のテストの副作用で本テストの URL が上書きされ「移行済みDB」に対して
       # upgrade が走り table credit_transactions__0033 already exists になる。
       # 本テストの URL を明示的に固定して他テストの影響を遮断する。
       monkeypatch.setenv("ALEMBIC_DATABASE_URL", sqlite_db_url)
       ...
   ```
2. `Config` 側の `set_main_option("sqlalchemy.url", ...)` も**両方**設定したままにする
   （env 側が優先されるため、env のみを正とする実装に合わせる）。
3. **実装側の防御も検討**: `src/backend/database/core.py:391` の
   `os.environ["ALEMBIC_DATABASE_URL"] = sync_url` はプロセス全体を汚染する。
   この関数の終了時に元の値へ復元する（`try/finally`）よう修正する。
   本番でも副作用が残らない方が安全であり、**これが本命の修正**。
   テスト側の隔離は**二重防御**として残す。

**リグレッション防止テスト**: `tests/regression/test_alembic_env_isolation.py` を作成:
1. **汚染再現テスト**: あらかじめ `ALEMBIC_DATABASE_URL` を「既に移行済みのダミーDB」に設定し、
   `test_migrations_up_down` と同様の処理（`Base.metadata.create_all` + `command.upgrade(head)`）を
   実行しても、**指定した新規URLに対して**マイグレーションが走ることを検証する。
   汚染が残っていれば `table ... already exists` で落ちる。
2. **副作用復元テスト**: `core.py` のマイグレーション関数を呼び出す前後で、
   `ALEMBIC_DATABASE_URL` が変わらないことを検証する（環境変数の保存・復元）。

**完了条件**:
```bash
# 単体（従来通り緑であること）
.venv/bin/python3 -m pytest tests/integration/test_migrations.py -q -p no:cacheprovider
# 全体（test_migrations_up_down が緑であること）
.venv/bin/python3 -m pytest tests/integration -q --timeout=180 -p no:cacheprovider \
  -W ignore::DeprecationWarning 2>&1 | grep -c "^FAILED"   # → 8
```

---

#### Step 5 — `real_db_manager` / conftest の後始末強化 ★

**目的**: グループ D の**再発を構造的に防ぐ**。Step 4 が「個別対症療法」なら、これは「根本対策」。

**手順**:
1. `tests/conftest.py` の `real_db_manager`（L117〜）が
   `DATABASE_URL` / `db_core.DATABASE_URL` / `_sync_engine` / `_sync_session_factory` を
   差し替えていることを確認し、**同様に以下の環境変数も保存・復元する**:
   - `ALEMBIC_DATABASE_URL`
   - `ENABLE_GRAPHRAG`（`tests/integration/test_graphrag_age.py:648` が `os.environ["ENABLE_GRAPHRAG"] = "true"` を直接書き込み、復元していない）
   - `AUTONOVEL_RAG_MODE` / `RAG_FALLBACK_MODE`
2. 復元は `try/finally` で行う（fixture の teardown）。
3. `tests/integration/test_graphrag_age.py:647-648` の
   `os.environ["DATABASE_URL"] = url` / `os.environ["ENABLE_GRAPHRAG"] = "true"` を
   `monkeypatch.setenv` に書き換える（pytest が自動復元）。

**リグレッション防止テスト**: `tests/regression/test_env_var_hygiene.py` を作成:
- リポジトリ全体を走査し、`os.environ["..."] = ` による**直接代入**が
  `tests/` 配下に残っていないことを検出する（`monkeypatch.setenv` への書き換えを強制）。
  例外は `try/finally` で復元している場合のみ許可し、許可リストを明示的に列挙する。
- さらに `os.environ.setdefault(...)` も対象に含める。

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_env_var_hygiene.py -q -p no:cacheprovider
.venv/bin/python3 -m pytest tests/integration -q --timeout=180 -p no:cacheprovider \
  -W ignore::DeprecationWarning 2>&1 | grep -c "^FAILED"   # → 8（Step 4 と同値を維持）
```

---

#### Step 6 — 順序依存の検出テスト（「単体では緑・全体で赤」を自動検出）★

**目的**: グループ D のような**順序依存バグを将来再発しても即座に検知する**。

**手順**:
1. `tests/regression/test_integration_order_dependency.py` を作成:
   - 対象テスト（現在は `test_migrations_up_down`）を **`tests/integration` 全体の後**に
     単独で再実行し、単独でも緑であることを検証する。
   - 実装方針: `subprocess` で `python -m pytest <target> -q` を起動し、
     事前に「汚染になり得るテスト」を走らせる。
   - **現実的な代替案（推奨）**: プロセス内で `ALEMBIC_DATABASE_URL` 等の
     危険な環境変数を人為的に汚染してから対象テストを実行し、隔離が機能していることを検証する。
     （完全な順序依存の再現は CI でしか安定しないため）
2. このテストは **Step 4・5 の隔離が壊れると即赤になる**ようにする。

**リグレッション防止テスト**: 本テスト自体がそれである。

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_integration_order_dependency.py -q -p no:cacheprovider
```

---

#### Step 7 — Phase 1 の総括確認

**目的**: Phase 1 の成果を固定し、Phase 2 への引き継ぎを行う。

**手順**:
1. 全検証コマンド（0.2）を実行し、結果を計画書の付録 B に記録する。
2. 期待値: 統合 **8 failed / 337 passed / 37 skipped**（`test_migrations` が緑化）。
3. `git status --short` で並行セッションの介入がないことを確認。

**リグレッション防止テスト**: なし（確認ステップ）。

**完了条件**: 付録 B が埋まっている。失敗数が 9 → 8 に減っている。

---

### Phase 2: `test_async_generation` の緑化（Step 8〜11）

#### Step 8 — グループ A の2バグを実測で確定 ★

**目的**: 修正の当たり所を推測で決めない。

**手順**:
1. 個別実行してエラーを捕捉:
   ```bash
   .venv/bin/python3 -m pytest \
     tests/integration/test_async_generation.py::test_generation_task_saves_to_specified_book_id \
     -q -p no:cacheprovider -W ignore::DeprecationWarning --tb=long 2>&1 \
     | grep -E "WARNING|ERROR|assert"
   ```
2. 確認すべき点:
   - **バグA**: `object CursorResult can't be used in 'await' expression` が
     `generation_tasks.py:427` のログで出ること
   - **バグB**: 続けて `generation_tasks.py:379 DB update failed ... status=failed` が出ること
   - `CreditService.__init__` に渡っている `credit_session` が同期 `Session` であること
   - `database.SessionLocal` が同期/非同期どちらのセッションファクトリかを確認する
     （`src/backend/database/core.py`）
3. **バグB の本当の原因を特定する**: `_update_task_in_db` の failed 経路だけが落ちる理由を、
   `repo.update_task_status`（`repository.py:285`、同期・`self.session.get`）と
   `database.SessionLocal()` の実体（同期 or 非同期）の不一致から特定する。
   ここが特定できなければ Step 10 は手当てだけで終わる。

**リグレッション防止テスト**: このステップ自体にテストはない（診断専用）。
確定した原因は Step 11 のテストで固定する。

**完了条件**: 付録 C に「バグAの原因」「バグBの原因」を1行ずつ書ける。

---

#### Step 9 — バグA修正: クレジット控除の同期/非同期不整合 ★

**目的**: `book_id` を渡す全経路が正常に完走するようにする。

**手順**:
1. `src/backend/tasks/generation_tasks.py:415` 周辺を修正する。
   方向性は次のいずれか（**Step 8 の診断結果で決める**）:
   - **(i)** `CreditService` に**非同期セッション**を渡す
     （`database.AsyncSessionLocal` 等、実体に応じて正しいものを選ぶ）
   - **(ii)** `deduct_credits` の呼び出しを**完全に同期化**する
     （同期版の内部実装を呼ぶ。`credit_service.py:75` の async 版内部で使っている
     セッションが同期なら、`_asyncio.run` ごと不要になる可能性が高い）
   - **(iii)** `_asyncio.run` の中で**専用の非同期エンジン/セッション**を生成して注入する
2. **注意**: ここは本番の課金経路。**片側だけ直して他経路（`deduct_credits_for_text_writing`
   等）を壊さないこと**。`src/integrations/billing/credit_service.py` の
   `deduct_credits` / `deduct_credits_for_text_writing` / `deduct_credits_for_illustration`
   の3つが同じ不整合を持っていないか確認する。
3. エラーログが消えていることを確認する。

**リグレッション防止テスト**: `tests/regression/test_credit_deduct_async_contract.py` を作成:
- `CreditService.deduct_credits` に渡すセッションが**非同期セッションである**ことを
  契約として検証する（`inspect.iscoroutinefunction(session.execute)` または
  セッションの型を検査）。
- または、モックの同期 `Session` を渡した場合に **例外ではなく明示的なエラー**になることを確認。
- **この契約テストが破れたら、`await CursorResult` のバグが再発したことを意味する。**

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_credit_deduct_async_contract.py -q -p no:cacheprovider
.venv/bin/python3 -m pytest tests/integration/test_async_generation.py -q -p no:cacheprovider \
  -W ignore::DeprecationWarning 2>&1 | grep -c "^FAILED"   # → 減っていること
```

---

#### Step 10 — バグB修正: タスク失敗時のステータス更新が記録されない ★

**目的**: どんなに失敗しても `pending` で止まらず、`failed` が必ず記録されるようにする。
**これは observability の欠陥**であり、本番でも「タスクが永久に pending のまま」になる障害に直結する。

**手順**:
1. `src/backend/tasks/generation_tasks.py:373-379` の `_update_task_in_db` を修正する。
   - `except Exception: session.rollback(); logger.exception(...)` が**失敗を握り潰している**。
   - **最低限**: このログに `task_id` と `status` だけでなく**例外の型とメッセージ**を残す。
   - **本質**: なぜ `update_task_status` が落ちるのか（Step 8 の診断結果）を直す。
2. **二重防御**: `_update_task_in_db` 内で1回失敗したら、
   **新しいセッションで再試行**するフォールバックを実装する
   （`session.close()` 後に `database.SessionLocal()` を作り直して再実行）。
   `pending` で永久停止を防ぐ最後の砦とする。
3. クレジット控除失敗 → `failed` 記録 → 元の `return {"error": ...}` という経路が
   **完走すること**を確認する。

**リグレッション防止テスト**: `tests/regression/test_task_status_never_stuck_pending.py` を作成:
- `_update_task_in_db(task_id, "failed")` を呼んだ後、
  **再取得したタスクの status が `pending` のまま残らない**ことを検証する。
- さらに、`_update_task_in_db` 内の DB 操作を **例外で汚染してから**呼び出し、
  フォールバックが機能して status が更新されることを検証する。
- **このテストが `pending` のままなら赤**（本計画で最も重要な保険の1つ）。

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_task_status_never_stuck_pending.py -q -p no:cacheprovider
.venv/bin/python3 -m pytest tests/integration/test_async_generation.py -q -p no:cacheprovider \
  -W ignore::DeprecationWarning
# → 2 failed が 0 になること（または Step 9 と合算で 0）
```

---

#### Step 11 — Phase 2 の総括確認

**手順**: 0.2 の全コマンドを実行し、付録 B を更新。
期待値: 統合 **6 failed**（8 − 2）。

**完了条件**: 失敗数 6。単体・回帰が前ステップ以下でない。

---

### Phase 3: `test_book_score_feedback_loop` の緑化（Step 12〜14）

#### Step 12 — PDCA 既定値が再生成ループを無効化することを実測で確定 ★

**手順**:
1. `src/generation/pdca_controller.py` 全文を読む。
   - `max_regenerations: int = 0`（L13）
   - `should_regenerate_full_text()`（L29-36）: `return self._regeneration_count < self.max_regenerations`
2. `src/domain/writing/coordinator.py:38,53` で `WritingService.__init__` が
   `pdca_controller` をどう初期化しているか（外部注入 or 既定生成）を確認する。
3. 個別実行でログを確認し、
   `PDCAポリシーにより全文再生成ループは無効化されています`（`coordinator.py:158-162`）
   の info レポートが出ていることを確認する。**これが出ていれば原因確定**。

**完了条件**: 付録 C に「`WritingService` が `max_regenerations=0` のコントローラを
どう受け取っているか」を書ける。

---

#### Step 13 — 実装修正: `auto_regenerate=True, max_retries=N` を尊重させる ★

**目的**: 呼び出し側の明示指定が無言で無視される状態を解消する。

**手順**:
1. **修正方針（本計画の指針「実装のバグなら実装を直す」に従う）**:
   `WritingService.generate_episodes(..., auto_regenerate=True, max_retries=N)` が明示指定された場合、
   `pdca_controller.max_regenerations == 0` の既定値によって**黙って無視されてはならない**。
   具体的には次のいずれか:
   - **(i) 推奨**: `generate_episodes` の `max_retries` 引数を
     PDCA コントローラの上限に反映する（`max_retries` が明示指定されたら
     `should_regenerate_full_text()` の判断に優先させる）。
   - **(ii)** `auto_regenerate=True` が明示指定された場合は
     `max_regenerations` の既定値を 0 にしない（呼び出し側が opted-in しているため）。
2. **本番挙動への影響を必ず確認する**:
   - `max_regenerations=0` が**意図的なコスト制御**として導入された経緯がないか
     （`git log -S "max_regenerations" -- src/generation/pdca_controller.py` で確認）。
   - 本番の呼び出し元が `auto_regenerate=True` を渡している箇所を洗い出し、
     修正後に**想定外の再生成ループが回り出してコスト爆発しないか**を確認する。
     回り出すようなら、本番呼び出し元の `auto_regenerate` を False に正すのが正しい修正。
3. **禁止事項**: `coordinator.py` のループ条件を緩めて
   「とりあえず2回呼ばれるようにする」等のテスト合わせ修正はしない。

**リグレッション防止テスト**: `tests/regression/test_pdca_respects_auto_regenerate.py` を作成:
- `WritingService(writer=..., book_score_calculator=..., score_threshold=70.0)`
  に `auto_regenerate=True, max_retries=3` を渡し、
  **`book_score_calculator.calculate` が最低1回呼ばれる**ことを検証する
  （現在は0回。これが本バグの直接的な症状）。
- さらに `auto_regenerate=False` の場合は **0回である**ことも検証する
  （オフがきちんと効いていること＝無条件に回り出す修正でないこと）。
- **両方向のテストがあることで、過剰修正と不十分修正の両方が検出できる。**

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_pdca_respects_auto_regenerate.py -q -p no:cacheprovider
.venv/bin/python3 -m pytest tests/integration/test_book_score_feedback_loop.py -q -p no:cacheprovider \
  -W ignore::DeprecationWarning
# → 2 failed が 0 になること
```

---

#### Step 14 — Phase 3 の総括確認

**手順**: 0.2 全コマンド実行 + 付録 B 更新。
期待値: 統合 **4 failed**（6 − 2）。

---

### Phase 4: `test_audit_aggregator_pipeline` の判定（Step 15〜16）

#### Step 15 — degraded ゲートが「実装バグ」か「正当な挙動」かを判定 ★

**目的**: ここだけは**即断せず、正当性を証明してから**手を下す。

**手順**:
1. 次を読む:
   - `src/agents/specialists/unified_auditor.py:25-60, 100-130`（degraded の定義とゲート）
   - `src/engine/audit/aggregator.py`（`next_agent` を返す経路）
   - `tests/integration/test_audit_aggregator_pipeline.py` 全文
2. **判定基準**:
   - LLM 未設定時に「評価が成立しない→合格扱いにせず戻す」が
     **コメントで意図的に書かれている**なら、それは**正当な防御**と判定する。
   - その場合、**実装は直さず、テストの setup を直す**:
     LLM 依存部分をスタブ化して `degraded=False` を返すようにし、
     **正常系（`next_agent == ILLUSTRATION`）を実際に検証できるようにする**。
     → 期待値は緩和しない（`ILLUSTRATION` のまま）。
   - もし「LLM 未設定でも degraded なのに合格扱いになる」等の
     **防御がすり抜ける経路**があれば、それは実装バグなので実装を直す。
3. **判断材料を付録 C に必ず残す**（後から「なぜテストを直したのか」を説明できるように）。

**完了条件**: 付録 C に「正当と判定した理由」または「実装バグと判定した理由」を書ける。

---

#### Step 16 — Step 15 の判定に従った修正とテスト ★

**手順**:
1. Step 15 の判定結果に従い、修正を1箇所だけ行う。
2. **リグレッション防止テスト**: `tests/regression/test_audit_degraded_gate_contract.py` を作成:
   - LLM 未設定（degraded）のとき、**`ILLUSTRATION` に進まないこと**
     （＝品質ゲートが機能していること）を検証する。
   - LLM 相当のスタブが `degraded=False` を返すとき、
     **`ILLUSTRATION` に進むこと**を検証する。
   - **この2方向のテストで、ゲートが「常に止まる」「常に通る」の
     どちらの過剰修正でも赤くなる。**

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_audit_degraded_gate_contract.py -q -p no:cacheprovider
.venv/bin/python3 -m pytest tests/integration/test_audit_aggregator_pipeline.py -q -p no:cacheprovider \
  -W ignore::DeprecationWarning
# → 0 failed
```
期待値: 統合 **3 failed**（4 − 1）。

---

### Phase 5: 残る2ファイル（Step 17〜20）

#### Step 17 — `test_reflective_rag` の空リスト原因を診断 ★

**手順**:
1. 個別実行し、握り潰しログを出す:
   ```bash
   .venv/bin/python3 -m pytest \
     tests/integration/test_reflective_rag_context_builder.py::test_context_builder_with_reflective_rag_success \
     -q -p no:cacheprovider -W ignore::DeprecationWarning --tb=long --log-cli-level=WARNING
   ```
   `src/agents/context_builder_agent.py:366-367` の
   `Reflective RAG retrieval failed: {e}` が出ているかを確認する。
2. 押さえる候補（コード読了で済むものから）:
   - `src/agents/context_builder_agent.py:341-367` の `retrieve_with_reflection` 呼び出し
     （`inspect.iscoroutine` 対応は既にある）
   - `src/integrations/rag/reflective_rag.py:469` の `search_similar_chunks` 呼び出し
     （L477 に `except` があり空の可能性）
   - `reflective_rag.py:492,590` の `score >= relevance_threshold` フィルタ
     （score は 0.95/0.92/0.88 なので通過するはず → **通過後に例外**の可能性が高い）
   - `retrieve_with_reflection` 内の**リフレクションループ**（`max_iter=2`）が
     LLM を呼んでいないか。LLM 未設定ならそこで落ちている可能性が高い。
3. **CI との差に注意**: CI は `AUTONOVEL_RAG_MODE=memory` / `RAG_FALLBACK_MODE=memory`。
   ローカルは未設定。**この差が原因なら、テストが環境依存**であり、
   テスト側で環境変数を固定する（Step 5 の後始末対象に追加済みのものを活かす）。

**完了条件**: 付録 C に空になる本当の原因を1行で書ける。

---

#### Step 18 — `reflective_rag` の修正とテスト ★

**手順**:
1. Step 17 の原因に従って修正する。
   **判断ルール**: LLM 未設定でリフレクションが成立しないなら、
   - 実装が**フォールバックしてでも文書を返すべき**なのに返さない → 実装を直す
   - リフレクション自体が LLM 必須で、未設定なら設計上空で正しい →
     テスト側に LLM 相当のスタブを注入し、**正常系を実際に検証する**
     （期待値 `len(rag_docs) > 0` と `doc-1 を含む` は**緩和しない**）
2. **リグレッション防止テスト**: `tests/regression/test_reflective_rag_returns_docs.py` を作成:
   - LLM 未設定（スタブ注入なし）でも `retrieve_with_reflection` が
     **例外を握り潰して空を返すのではなく**、明示的な結果（documents or エラー）を返すこと。
   - スタブ注入時には `len(documents) > 0` であること。
   - **「常に空」が検出される。**

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_reflective_rag_returns_docs.py -q -p no:cacheprovider
.venv/bin/python3 -m pytest tests/integration/test_reflective_rag_context_builder.py -q -p no:cacheprovider \
  -W ignore::DeprecationWarning   # → 0 failed
```
期待値: 統合 **2 failed**（3 − 1）。

---

#### Step 19 — `test_relational_memory_e2e` の2症状を診断 ★

**手順**:
1. **症状1（line 210, `assert 0 == 1`）**:
   - `src/engine/foreshadowing/service.py:67-69`:
     `unresolved = await self.repo.get_unresolved(book_id)` が空なら即 `return []`。
   - テストの「設置（Step 1〜4）」が実際に repo に保存されているかを、
     `get_unresolved` のクエリ条件（status フィルタ / book_id / user_id）と突き合わせる。
   - 特に **`user_id` 追加（過去の緑化で seed へ user_id を追加した経緯）** が
     `get_unresolved` のフィルタに影響していないかを確認する。
2. **症状2（line 389, `DID NOT RAISE`）**:
   - テストのコメントは「**実装では例外が伝播するため、呼び出し側でtry/exceptが必要**」と
     明記しているのに、実装側は握り潰している。
   - `episode_context_builder.build_context` の例外処理を読み、
     **どちらの意図が現行コードに反映されているか**を確認する。
   - **判定**:
     - 例外を握り潰すのが現行の設計 → テストのコメントが陳腐化。
       ただし**「握り潰して空で返ること」を検証するテストに書き換える**のは
       **検知力の低下を伴う**ため、付録 C に正当性を記録した上で行う。
     - 例外を伝播するのが設計 → 実装を直す（**本計画の指針に従いこちらを優先**）。
3. **2症状が同一原因の可能性**（初期化/シード失敗が全経路を空にしている）に注意。
   症状1を先に直し、症状2が同時に直るかを確認する。

**完了条件**: 付録 C に2症状それぞれの原因と、症状2の判定理由を書ける。

---

#### Step 20 — `relational_memory` の修正とテスト ★

**手順**:
1. Step 19 の判定に従って修正する。
2. **リグレッション防止テスト**: `tests/regression/test_relational_memory_contract.py` を作成:
   - **伏線の「設置」が `get_unresolved` に必ず現れること**を検証する
     （設置→取得のラウンドトリップ。これが破れたら症状1の再発）。
   - `build_context` の DB 例外時挙動を、**Step 19 の判定に一致する**形で検証する
     （伝播するなら `pytest.raises`、握り潰すなら空返却＋ログ出力を検証）。
     **どちらか一方だけを検証するのではなく、判定結果とテストが
     常に一致していることを保証するコメントを付す。**

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_relational_memory_contract.py -q -p no:cacheprovider
.venv/bin/python3 -m pytest tests/integration/test_relational_memory_e2e.py -q -p no:cacheprovider \
  -W ignore::DeprecationWarning   # → 0 failed
```
期待値: 統合 **0 failed / 345 passed / 37 skipped**。

---

### Phase 6: ゲート化（Step 21〜24）

#### Step 21 — CI 上での全件緑を実測する（ゲート化の通過条件）★★

**目的**: **ローカルで緑でも CI で赤になるリスク（0.4）を現実に潰す。**
ここが通らなければ Step 22 は**実行してはならない**。

**手順**:
1. Phase 1〜5 の全変更をコミット & プッシュする。
2. GitHub Actions 上で `integration-observe` ジョブを実行する。
   （このジョブは `continue-on-error: true` のままなので、失敗してもブランチは壊れない）
3. **確認する項目**:
   - [ ] `pytest tests/integration` の結果が **0 failed** か
   - [ ] **収集エラー（SyntaxError 等）が0件か**
   - [ ] `37 skipped` が想定通りか（Docker なし環境由来の skip）
   - [ ] PostgreSQL 固有の失敗が出ていないか（ローカルは SQLite のため検出不可能）
   - [ ] `ALEMBIC_DATABASE_URL` 汚染が CI でも再現しなかったか（Step 4 の検証）
4. **赤の場合**: Phase へ戻って原因を特定し、**Step 22 は実行しない**。
   付録 D に CI での失敗リストを貼り付ける。

**リグレッション防止テスト**: なし（実測ステップ）。

**完了条件**: CI 上で `0 failed / 収集エラー 0件`。

---

#### Step 22 — `continue-on-error: false` への切り替え（ゲート化）★★★

**目的**: 本計画の最終目的を達成する。

**手順**:
1. `.github/workflows/ci.yml` を修正する:
   ```yaml
   # 変更前
   integration-observe:
     runs-on: ubuntu-latest
     continue-on-error: true

   # 変更後
   integration:
     runs-on: ubuntu-latest
     continue-on-error: false
   ```
2. **ジョブ名を `integration-observe` → `integration` に変更する**。
   理由: `observe`（観測）という名前が残ると、後から「これは観測用だから失敗してもよい」
   と誤読される。**名前自体から「観測」の語を消す**。
3. ステップ名も `Run integration suite (observe)` → `Run integration suite` に変更する。
4. **Step 3 で書いたコメントを「未達」→「ゲート有効」に書き換える**:
   ```
   # 統合テストゲート（本計画: plans/PLAN_GATE_INTEGRATION_24STEPS.md）
   # 状態: green —— tests/integration の0 failed をブランチ保護の必須条件とする。
   # 再び failed が1件でも出たら、このジョブを continue-on-error: true に戻すのではなく、
   # 速やかに原因を修正する。「観測モード」への退避は禁止（docs/TEST_GATE_POLICY.md）。
   ```
5. `docs/TEST_GATE_POLICY.md` の状態を `未達` → `green` に更新する。
6. **ブランチ保護ルール**に `integration`ジョブを追加するようユーザーに依頼する
   （GitHub の設定画面が必要なため、この計画の範囲外。**手順として明記する**）。

**リグレッション防止テスト**: `tests/regression/test_ci_gate_enforced.py` を作成:
- `.github/workflows/ci.yml` を YAML としてパースし、
  `integration`（旧 `integration-observe`）ジョブが
  **`continue-on-error: true` を持たないこと**を検証する。
- さらに `integration` ジョブが **`tests/integration` を実行するステップを持つ**こと、
  **postgres と redis のサービスを持つ**ことを検証する。
- **このテストが赤なら「ゲートが外された」ことを意味する**（本計画で最も重要な保険）。

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_ci_gate_enforced.py -q -p no:cacheprovider
grep -n "continue-on-error" .github/workflows/ci.yml   # integration 行に true が残っていないこと
```

---

#### Step 23 — 失敗数ラチェットの CI 上での有効化 ★

**目的**: Step 2 で作った基準ファイルを**実際に効かせる**。

**手順**:
1. `tests/regression/test_gate_integration_ratchet.py` を拡張し、
   **CI 環境でのみ**以下を検証する:
   ```python
   @pytest.mark.skipif(not os.environ.get("CI"), reason="CI のみで判定（ローカルに postgres/redis なし）")
   def test_integration_failure_count_within_baseline():
       # pytest を subprocess で起動し、FAILED 数を数える
       # config/integration_failure_baseline.json の max_failed 以下であることを検証
   ```
   - **ゲート化後は `max_failed` を `gate_target_failed = 0` に更新する**
     （ラチェットが「0を超えてはならない」ことを保証する）。
2. `config/integration_failure_baseline.json` の `max_failed` を **9 → 0** に更新する。
   `known_failures` 配列は**空配列**にする。
   → 「既知失敗」の概念そのものを消し、**1件も許容しない**状態にする。
3. `docs/TEST_GATE_POLICY.md` にラチェットの運用ルールを追記:
   - 失敗数が増えることは**絶対に許可しない**
   - どうしても緑にできない場合は `max_failed` を増やすのではなく、
     **計画を立て直してから** `continue-on-error: true` に戻し、
     `docs/TEST_GATE_POLICY.md` に **「未達」** と明記する

**リグレッション防止テスト**: 本テスト自体がそれである。
さらに `known_failures` が空でない場合に赤になる追加テストを置く
（「既知失敗」リストの復活を検出する）。

**完了条件**:
```bash
.venv/bin/python3 -m pytest tests/regression/test_gate_integration_ratchet.py -q -p no:cacheprovider
python3 -c "import json;d=json.load(open('config/integration_failure_baseline.json'));assert d['max_failed']==0 and d['known_failures']==[]"
```

---

#### Step 24 — 最終検証と「未達」フォールバックの明文化 ★

**目的**: 本計画の完了宣言と、**万一ゲート化できない場合の手順を確定する**。

**手順**:
1. **全検証を1回通す**:
   ```bash
   .venv/bin/python3 -m pytest tests/integration -q --timeout=180 -p no:cacheprovider \
     -W ignore::DeprecationWarning
   .venv/bin/python3 -m pytest tests/unit -q -p no:cacheprovider
   .venv/bin/python3 -m pytest tests/regression -q -p no:cacheprovider
   .venv/bin/python3 -m pytest tests/integration --collect-only -q -p no:cacheprovider
   ```
2. **CI を再実行**し、`integration` ジョブが緑であることを確認する。
3. 付録 A（基準）/ B（各Phase結果）/ C（原因と判定理由）/ D（CI 実測結果）を埋め、
   本計画の先頭に **「完了」または「未達」** のバッジを付ける。

##### ★ フォールバック: ゲート化ができない場合の手順（必ず守る）

Step 21 が通らないまま Step 22 を実行しては**ならない**。
その場合、以下を**順に**実施する:

1. **`continue-on-error: true` のままにする**（＝ゲートは外さない）。
2. **ジョブ名を `integration-observe` のままにせず、`integration-unmet` に変更する**。
   「observe（観測）」という語を使わないため。
3. `.github/workflows/ci.yml` のコメントに次を**正確に**書く:
   ```
   # 状態: 未達
   # 未達項目: <失敗テストの完全なリスト>
   # 未達理由: <1行で>
   # 解除条件: <何が通れば green か>
   # 計画: plans/PLAN_GATE_INTEGRATION_24STEPS.md
   #
   # ※ このジョブは continue-on-error: true であり、ブランチ保護の条件ではない。
   #    「観測モード」「既知失敗」「許容範囲」と呼び換えることは禁止。
   ```
4. `docs/TEST_GATE_POLICY.md` の状態を `未達` とし、上記と同じ内容を記載する。
5. `tests/regression/test_ci_gate_enforced.py` は**緑のままにする**（
   `continue-on-error: true` が残っていることを検証するバージョンではなく、
   **「コメントに『未達』が書かれていること」を検証するバージョン**を実装する）。
   → つまり **どちらの場合でも「言葉が正しいか」はテストされる**。

**完了条件**: 付録 E に「完了」または「未達（+ 理由と解除条件）」のどちらかが明記されている。

---

## 3. ステップ一覧と期待される失敗数の推移

| Step | 内容 | 期待 failed 数 | タイプ |
|---|---|---|---|
| 1 | 現状スナップショット固定 | 9 | 準備 |
| 2 | ラチェット基準ファイル + 構造健全性テスト | 9 | ★リグレッション防止 |
| 3 | 「未達」表記ルール + docs テスト | 9 | ★未達明記 |
| 4 | `ALEMBIC_DATABASE_URL` 隔離 | **8** | ★修正 |
| 5 | conftest 環境変数の後始末強化 | 8 | ★再発防止 |
| 6 | 順序依存の検出テスト | 8 | ★リグレッション防止 |
| 7 | Phase 1 総括 | 8 | 確認 |
| 8 | グループA 診断 | 8 | 診断 |
| 9 | バグA修正（await/sync） | 7 | ★修正 |
| 10 | バグB修正（pending 永久停止） | **6** | ★修正 |
| 11 | Phase 2 総括 | 6 | 確認 |
| 12 | PDCA 原因確定 | 6 | 診断 |
| 13 | `auto_regenerate` 尊重 | **4** | ★修正 |
| 14 | Phase 3 総括 | 4 | 確認 |
| 15 | degraded 判定 | 4 | 判定 |
| 16 | 判定に従った修正 | **3** | ★修正 |
| 17 | reflective_rag 診断 | 3 | 診断 |
| 18 | reflective_rag 修正 | **2** | ★修正 |
| 19 | relational_memory 診断 | 2 | 診断 |
| 20 | relational_memory 修正 | **0** | ★修正 |
| 21 | **CI での全件緑実測** | 0 | ★★★ 通過条件 |
| 22 | **`continue-on-error: false` 切り替え** | 0 | ★★★ ゲート化 |
| 23 | ラチェット `max_failed = 0` | 0 | ★再発防止 |
| 24 | 最終検証 + 未達フォールバック確定 | 0 | 完了宣言 |

**リグレッション防止テストは 12ファイル**（Step 2, 3, 4, 5, 6, 9, 10, 13, 16, 18, 20, 22 で新規作成。
Step 23 は Step 2 の `test_gate_integration_ratchet.py` を拡張するためファイル数は増えない）。
すべて `tests/regression/` に置き、**単体・回帰の緑に含めて毎回実行される**。

---

## 4. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| **並行セッションとの競合** | 自分の修正が上書き・消される | 0.3 の遵守事項。編集前に `git status` 確認。`stash@{0}` / `src/agents/audit_agent/` は触らない |
| **ローカル緑 ≠ CI 赤** | ゲート化後ブランチが赤くなり続ける | Step 21 を**絶対の通過条件**にする。通らなければ 24 のフォールバック |
| **SyntaxError の再発** | 収集エラーで全件落ちる | 全ステップの完了条件に `--collect-only` 成功を含める（0.3） |
| **課金経路の回帰**（Step 9） | 本番の課金が壊れる | `credit_service.py` の3メソッドを一括確認。回帰テストを併設 |
| **再生成コスト爆発**（Step 13） | 本番でループが回り出す | `auto_regenerate=False` の**逆方向テスト**を必ず書く |
| **テスト緩和の誘惑** | 検知力が落ちる（既に前科あり） | 0.3 原則1。期待値の変更は付録 C に理由を記録する義務 |
| **Docker なし** | 一部テストが skip のまま | `37 skipped` が変化しないことを確認し、skip の増加を「改善」と称さない |

---

## 5. 付録

### 付録 A: ベースライン（Step 1 で記録）

```
基準コミット: 4aa42338
実行: .venv/bin/python3 -m pytest tests/integration -q --timeout=180 -p no:cacheprovider
結果: 9 failed / 336 passed / 37 skipped（3回実行すべて同一）

FAILED tests/integration/test_async_generation.py::test_generation_task_saves_to_specified_book_id
FAILED tests/integration/test_async_generation.py::test_generation_task_creates_new_book_when_book_id_not_provided
FAILED tests/integration/test_audit_aggregator_pipeline.py::test_audit_aggregator_pipeline_integration
FAILED tests/integration/test_book_score_feedback_loop.py::test_writing_service_regeneration_loop_success
FAILED tests/integration/test_book_score_feedback_loop.py::test_writing_service_regeneration_max_retries
FAILED tests/integration/test_migrations.py::test_migrations_up_down
FAILED tests/integration/test_reflective_rag_context_builder.py::test_context_builder_with_reflective_rag_success
FAILED tests/integration/test_relational_memory_e2e.py::TestRelationalMemoryE2E::test_foreshadowing_lifecycle_plant_to_resolve
FAILED tests/integration/test_relational_memory_e2e.py::TestRelationalMemoryE2E::test_error_handling_in_pipeline
```

**単体**: 8075 passed / **回帰**: 620 passed（既知失敗8件: `conftest_fixtures`, `docs_router_count`,
`subprocess_encoding_gate`, `tier_quality_gate`×4, `v5_version_consistency`）

### 付録 B: 各 Phase の結果（実装時に記録）

- Phase 1 後: _(未記入)_
- Phase 2 後: _(未記入)_
- Phase 3 後: _(未記入)_
- Phase 4 後: _(未記入)_
- Phase 5 後: _(未記入)_
- Phase 6 後: _(未記入)_

### 付録 C: 原因と判定理由（Step 8, 12, 15, 17, 19 で記録）

- グループ A バグA: _(未記入)_
- グループ A バグB: _(未記入)_
- グループ B: _(未記入)_
- グループ C 判定: _(未記入)_
- グループ E: _(未記入)_
- グループ F 症状1: _(未記入)_
- グループ F 症状2 判定: _(未記入)_

### 付録 D: CI 実測結果（Step 21 で記録）

_(未記入)_

### 付録 E: 最終ステータス（Step 24 で記録）

- 状態: **未達**（計画作成時点。実装完了後に `完了` へ更新する）
- 理由: 本計画は未着手
- 解除条件: Step 21 の CI 実測で 0 failed が確認でき、Step 22 が完了すること
