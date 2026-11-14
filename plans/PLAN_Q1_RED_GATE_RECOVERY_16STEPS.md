# PLAN_Q1: 赤いゲートの復旧 (16 STEPS)

> **目的**: main (HEAD = `1538189a`) で**現在赤になっている品質ゲートを全て緑に戻す**。
> 失敗の原因を「本番バグ / テスト陳腐化 / デッドコード上のテスト」に分類し、
> 分類ごとに正しい治し方で治す。最後に**同じ赤が再発しない構造ゲート**を入れて閉じる。
>
> **実測日**: 2026-11-15（全て本ワークツリーで実行した実測値。推測値は書かない）
> **前提文書**: `docs/STATUS.md` / `docs/TEST_GATE_POLICY.md` / `config/ci_lint_baseline.json`
> **後続計画**: `PLAN_Q2`（デッドコード削除）→ `PLAN_Q3`（shim 焼却）。**必ず本計画を先に完了する。**
> **作業方針**: 1 ブランチ・直列実行。1 Step = 1 コミット（テスト更新は実装変更と**同一コミット**に含める — §3 P2）。

---

## 1. 実測データ（2026-11-15 時点）

### 1-1. ゲートの現状

| ゲート | baseline | 実測 | 判定 | 備考 |
|---|---:|---:|:---:|---|
| ruff (`ruff check src tests config scripts`) | 85 | **170** | **FAIL** | baseline コミット `215f1266` を worktree 実測で 85 件確認 → その後 5 日間（`215f1266..HEAD`、453 ファイル +32,885 行）で **+85 件の劣化がコミットされた** |
| mypy (`mypy src`, CI ピン `mypy==2.3.1`) | 952 | **388 / 196 files** | PASS | baseline が**陳腐に緩い**（コミット `b2b2ca17` で半減済みだが baseline 未更新）。なお venv の mypy 2.4.1 では 514 件 — **ローカルと CI でツールバージョンが不一致** |
| ruff format (`--check src`) | 0 | 0 | PASS | — |
| pytest tests/unit | 全緑が前提 | **15 failed / 8,342 passed**（422 秒） | **FAIL** | 内訳は §1-2 |
| ratchet の設計上の欠陥 | — | — | ⚠ | `scripts/ci_lint_ratchet.py` は「減少時に baseline を自動引き下げ」するが、**CI 上ではコミットされず消失する**。引き下げはローカル実行 + コミットでのみ永続化される |

### 1-2. unit 15 失敗の分類（全件の根本原因を実測済み）

**分類**: A = 実装バグ（コードを直す）/ B = テスト陳腐化（テストを直す）/ C = デッドコード上のテスト（Q2 で一緒に消す）

| # | テスト | 分類 | 根本原因（証拠） |
|---|---|:---:|---|
| 1-5 | `tests/unit/test_worker_recovery.py`（5 件） | **A** | `src/backend/tasks/worker_recovery.py:98` が `TaskWALLogModel.worker_id` を参照するが、**ORM モデルに `worker_id` 列が存在しない**（`src/infrastructure/database/models/task_wal_log_model.py:13-21`）。マイグレーション `0036_task_wal_logs_worker_id.py` は存在するが、H12 コミット `3882043c` が **ORM 側の変更を漏らした**（変更ファイルは migration / worker_recovery / 新規テストの 3 件のみ）。**本番でも AttributeError で heartbeat 更新が落ちる実バグ** |
| 6 | `tests/unit/test_dag_scheduler_part5.py::test_dag_scheduler_huey_dispatch` | B | H10 (`c69fde5f`) で Huey タスク署名を `(node_name=..., payload=...)` に修正済み。テストは**修正前の壊れた署名** `(func_name=..., kwargs=..., node_id=...)` を assert している（壊れ方を固定したテストになっている） |
| 7-8 | `tests/unit/routers/test_router_novel_coverage.py`（2 件） | B | H15 (`4ae7059c`) で `produce_novel` から `require_api_key` 二重依存を削除済み。テストが廃止済み kwarg `api_key="key"` を渡す |
| 9-10 | `tests/unit/test_easy_mode_router.py`（2 件） | B | H9 (`def45684`) / Step 10 (`1538189a`) で「task_id を投入前に生成し DB 行を先に作る」方式に変更。テストは Huey enqueue の返り値 ID (`test-huey-id`) を期待するが、実装は router 生成 UUID を返す（実測: メッセージ内 ID = `d18ca79c-…`） |
| 11 | `tests/unit/api/test_easy_mode_api.py::test_export_with_data_api` | B | C1 IDOR 対策で `export_with_data_endpoint` に `verify_book_ownership(book_id, current_user)` と `current_user` 依存を追加済み（`src/backend/routers/easy_mode.py:652-672`）。テストは所有権のない `book_id=99` で呼ぶため 404 |
| 12-13 | `tests/unit/test_asset_pack_deep.py::test_asset_pack_generator_init_components` / `tests/unit/easy_mode/test_asset_pack_generator_extra.py::TestGraphOutputs::test_init_components` | B | H13 (`1acb6d3a`) で `_init_components` に `output_dir` 引数を追加済み。テストは旧シグネチャで呼ぶ |
| 14 | `tests/unit/llm/adapters/test_llm_adapters_extra.py::test_factory_openai` | B | factory に「`base_url` 単独指定は `ValueError`（サーバーキー流出防止）」のセキュリティバリデーション追加済み（`src/llm/adapters/factory.py:95`）。テストは `base_url` のみで呼ぶ |
| 15 | `tests/unit/llm/clients/test_api_clients.py::TestOpenAIGenerateJson::test_success_without_schema` | **C** | 対象 `src/llm/clients/` は **src からの実 import がゼロのデッドモジュール**（PLAN_Q2 Step 8 で削除）。本計画では「既知の赤」として登録するだけにする |

### 1-3. ruff 170 件の内訳（`--statistics` 実測）

| ルール | 件数 | 処理方針 |
|---|---:|---|
| F401 unused-import | 88 | `--fix` で自動修正（ただし再エクスポート箇所は per-file-ignores が既に効いている前提で確認） |
| F841 unused-variable | 28 | `--fix --unsafe-fixes` の判断箇所は手動確認（代入副作用の有無を目視） |
| E741 ambiguous-variable-name | 13 | 手動リネーム（`l` → `line` 等） |
| F811 redefined-while-unused | 10 | 手動（再定義の意図確認。意図的なら削除） |
| E712 true-false-comparison | 10 | 手動（`== True` → `is True` / 真偽値そのまま） |
| E701 multiple-statements-on-one-line | 7 | 手動（改行） |
| W293 / F601 / W605 / E711 / F403 | 14 | 手動（少量） |
| **F821 undefined-name** | **1** | **実バグの疑い**: `scripts/detect_flaky.py:29` — `Undefined name 'e'`。Step 10 で重点調査 |

### 1-4. xpassed（非 strict xfail）

`tests/unit` 実行で **3 xpassed** を確認。xfail が外れて通っているテストは「失敗するはずが通った」状態であり、放置すると仕様の固定が曖昧になる。Step 13 で全件 xfail を外すか strict 化する。

---

## 2. 目的・スコープ

### 目的
1. unit 15 失敗を「分類 A/B/C それぞれの正しい方法」で解消し、**unit suite を緑に戻す**
2. ruff 170 → 0 にして ratchet baseline を更新し、**静的解析ゲートを緑に戻す**
3. mypy baseline を実測値（CI ピン版での値）に更新し、**ローカル / CI のツールバージョンを統一する**
4. 「ORM とマイグレーションの乖離」「テスト未更新のままのインターフェース変更」を**構造的に検出する回帰ゲート**を新設する

### スコープ内
- `tests/unit` の 15 失敗、ruff 170 件、mypy baseline 更新、ツールバージョンピン
- 上記の再発防止ゲート（新規テスト 3 本 + Makefile 拡張）

### スコープ外（別計画）
- `tests/integration` / `tests/e2e` の全量実行確認（PG + Redis 必須。CI 結果の確認のみ Step 16 で行う）
- デッドコード削除（PLAN_Q2）、shim 削除（PLAN_Q3）
- mypy 388 件の中身の削り込み（baseline 更新まで。ゼロ化は別計画）

---

## 3. プリンシプル

| # | プリンシプル | 根拠 |
|---|---|---|
| P1 | **分類を先に、修正は後。** A はコード修正、B はテスト修正、C は削除予約。混ぜない | 「テストを消して緑にする」事故の防止 |
| P2 | **インターフェース変更とテスト更新は同一コミット。** この規律違反が今回の赤の直接原因（H9/H10/H13/H15/C1 いずれも実装コミットにテスト更新が欠落） | `3882043c` 等の変更ファイル一覧が証拠 |
| P3 | **テストの assert は現在の正しい仕様を固定する。** 古い壊れた挙動を assert したテスト（#6）は更新時に仕様を明記する | #6 の教訓 |
| P4 | **ゲートの baseline 変更は README と同一コミット**（CI の README 整合チェックが fail するため） | `.github/workflows/ci.yml` の README チェック |
| P5 | **baseline 引き下げはローカルで `--update` 実行 + コミット。** CI の自動引き下げは消失することを確認済み | §1-1 の設計欠陥 |
| P6 | 各 Step の完了条件は**コマンドと期待結果**で記述する | PLAN_R3 P6 を継承 |
| P7 | 実行前に `git status` で clean を確認する | PLAN_R3 P7 を継承 |

---

## 4. ステップ詳細

### Phase A: 現状固定（Steps 1-2）

#### Step 1: 失敗インベントリの確定

- **内容**: 本計画 §1-2 の分類表を `plans/` 配下に確定版として残す（本ファイル自体がインベントリ）。実行コマンドをコメントとして記録:
  ```bash
  .venv/bin/python -m pytest tests/unit -q --timeout=120 --tb=no 2>&1 | grep "^FAILED"
  ```
- **完了条件**: 上記コマンドの FAILED 行数 = 15、かつ分類表の 15 件と一致
- **コミット**: `docs(q1): unit 15 失敗の根本原因インベントリ（分類 A5/B9/C1）`

#### Step 2: ruff インベントリの確定

- **内容**: §1-3 の統計とファイル別分布を確定:
  ```bash
  .venv/bin/python -m ruff check src tests config scripts --statistics
  .venv/bin/python -m ruff check src tests config scripts --output-format=concise | awk -F: '{print $1}' | sort | uniq -c | sort -rn
  ```
- **完了条件**: 統計の合計 = 170
- **コミット**: `docs(q1): ruff 170 件の内訳と修正方針`

### Phase B: 実装バグ修正（分類 A / Steps 3-4）

#### Step 3: `TaskWALLogModel` に `worker_id` を追加 + ORM↔migration 整合回帰テスト新設

- **対象**: `src/infrastructure/database/models/task_wal_log_model.py`
- **変更**:
  ```diff
  +    worker_id = Column(String(64), nullable=True, index=True)
       created_at = Column(CompatibleDateTime, server_default=func.now())

       __table_args__ = (
  +        Index("idx_task_wal_logs_worker_id", "worker_id"),
           Index("idx_task_wal_logs_dag_id", "dag_id"),
  ```
  - マイグレーション `0036_task_wal_logs_worker_id.py` は既存（`nullable=True`）なので **DB 側の変更は不要**。ORM の欠落のみを埋める
- **新規回帰テスト**: `tests/regression/test_model_migration_parity.py`
  - 設計: Alembic を SQLite 一時 DB に `upgrade head` した後、**各 ORM モデルの `__table__` のカラム名集合**と**実 DB の `PRAGMA table_info` の列集合**を全テーブル分照合し、差分があれば fail（ORM にのみ列 / DB にのみ列の両方向を検出）
  - 実装上の注意: SQLite 固有型（`CompatibleDateTime` 等）は名前比較ではなく「列名集合」比較にする。`alembic_version` テーブルは除外
  - この 1 本で H12 型の事故（migration だけ追加 / ORM だけ追加）を**両方向**で構造的に防ぐ
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_model_migration_parity.py -q          # 1 passed
  .venv/bin/python -m pytest tests/unit/test_worker_recovery.py -q                       # 5 passed
  .venv/bin/python -m pytest tests/unit/tasks/ -q                                        # 全緑（既存 zombie 回帰含む）
  ```
- **コミット**: `fix(q1): TaskWALLogModel に worker_id 列を追加（H12 の ORM 漏れ）+ ORM↔migration 整合回帰テスト`

#### Step 4: Phase B クローズ確認

- **完了条件**: `pytest tests/unit -q --timeout=120` の failed が **15 → 10**（分類 B 9 件 + C 1 件のみ残る）
- **コミット**: なし（Step 3 のコミットに含まれる。検証のみ）

### Phase C: テスト陳腐化の解消（分類 B / Steps 5-8）

#### Step 5: DAG scheduler テストを現仕様に更新

- **対象**: `tests/unit/test_dag_scheduler_part5.py::test_dag_scheduler_huey_dispatch`
- **変更**: assert を H10 後の正仕様に更新:
  ```python
  mock_exec.assert_called_once_with(
      node_name="agent_review",
      payload={"draft": "Some draft", "task_id": "huey_node"},
  )
  ```
  - コメントで仕様を固定: 「H10 (c69fde5f) 以降、DAG Huey タスクは `(node_name, payload)` 署名。`task_id` は payload に同梱され、投入前に DB 行が作られる（H9）」
- **完了条件**: `pytest tests/unit/test_dag_scheduler_part5.py -q` → 全緑
- **コミット**: `test(q1): DAG Huey タスク署名テストを H10 後の正仕様に更新`

#### Step 6: `produce_novel` テストを新シグネチャに更新

- **対象**: `tests/unit/routers/test_router_novel_coverage.py`（2 件）
- **変更**: `produce_novel(req, api_key="key")` → `produce_novel(req)`。あわせてテスト冒頭に H15 の意図（API キー依存の二重化解消。認証はグローバルミドルウェアに一本化）をコメントで記録
- **完了条件**: `pytest tests/unit/routers/test_router_novel_coverage.py -q` → 全緑
- **コミット**: `test(q1): produce_novel テストを H15 後のシグネチャに更新`

#### Step 7: easy_mode task_id / export-with-data テストを H9/C1 仕様に更新

- **対象**: `tests/unit/test_easy_mode_router.py`（2 件）+ `tests/unit/api/test_easy_mode_api.py::test_export_with_data_api`
- **変更**:
  1. task_id 系: モックを「router が先に生成する task_id」に合わせる。テストを強化し、**(a) 返却メッセージにその task_id が含まれる、(b) enqueue より前に DB 行が作られる**（H9 の回帰を二重に固定）
  2. export-with-data 系: `verify_book_ownership` を満たすよう、テスト内で `book_id` をモックユーザー（id=1）所有の書籍として作成するか、`dependency_overrides` で所有権検証を差し替える。**所有権検証そのものを削らない**（C1 はセキュリティ修正）
  3. 直呼び出しテスト（`test_export_with_data_endpoint`）には `current_user` を渡す
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/unit/test_easy_mode_router.py -q        # 全緑
  .venv/bin/python -m pytest tests/unit/api/test_easy_mode_api.py -q       # 全緑
  ```
- **コミット**: `test(q1): easy_mode の task_id 先付与・export 所有権検査（C1）仕様にテストを追従`

#### Step 8: asset_pack 2 件 + factory バリデーション 1 件の更新

- **対象**:
  - `tests/unit/test_asset_pack_deep.py::test_asset_pack_generator_init_components`
  - `tests/unit/easy_mode/test_asset_pack_generator_extra.py::TestGraphOutputs::test_init_components`
  - `tests/unit/llm/adapters/test_llm_adapters_extra.py::test_factory_openai`
- **変更**:
  1. asset_pack: `_init_components(series, output_dir=...)` に新引数を渡す（H13 シグネチャ）
  2. factory_openai: `get_llm_adapter("openai", base_url="http://x", api_key="test-key")` に修正。**加えて回帰テストを新設**:
     ```python
     def test_factory_rejects_base_url_without_api_key():
         with pytest.raises(ValueError, match="api_key"):
             get_llm_adapter("openai", base_url="http://x")
     ```
     （セキュリティバリデーションが将来誤って緩められることを防ぐ固定）
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/unit/test_asset_pack_deep.py tests/unit/easy_mode/test_asset_pack_generator_extra.py tests/unit/llm/adapters/ -q   # 全緑
  ```
- **コミット**: `test(q1): asset_pack 新シグネチャ対応 + factory の api_key 必須バリデーション回帰テスト新設`

#### Step 9: 分類 C（1 件）を「既知の赤」として登録

- **内容**: `tests/unit/llm/clients/test_api_clients.py::TestOpenAIGenerateJson::test_success_without_schema` は、PLAN_Q2 Step 8（`src/llm/clients/` 丸ごと削除）で消える。本計画では触らない
- **リスク**: Q2 を実行するまで赤が 1 件残る。Step 14 の予算 JSON に「既知 1 件」として登録し、**Q2 完了時に予算 0 へ引き下げる**
- **完了条件**: 上記 1 件以外の unit 全緑:
  ```bash
  .venv/bin/python -m pytest tests/unit -q --timeout=120   # 1 failed（既知 C）のみ / 14 件解消
  ```
- **コミット**: `docs(q1): 分類C 1件を Q2 削除対象として既知の赤に登録`

### Phase D: ruff バーンダウン（Steps 10-12）

#### Step 10: ruff safe fix 一括適用

- **コマンド**:
  ```bash
  .venv/bin/python -m ruff check src tests config scripts --fix
  .venv/bin/python -m ruff format src    # format_files=0 維持の確認
  .venv/bin/python -m pytest tests/unit -q --timeout=120   # Step 9 の状態と同じ（1 failed）であること
  ```
- **注意**: F401 自動削除で `__init__.py` 系は per-file-ignores が効いているはずだが、**削除された import が実は再エクスポートだった**場合に ImportError が出る。unit suite 全実行で検証する（P3 の `**/__init__.py` ignore に頼りすぎない）
- **完了条件**: ruff 件数が 170 → **73 前後**（safe fix 分）、unit suite の失敗数が増えていない
- **コミット**: `style(q1): ruff safe fix 一括適用（F401/F841 自動修正）`

#### Step 11: ruff 手動修正（F821 の実バグ調査を含む）

- **対象**: E741 13 / E712 10 / E701 7 / F601 4 / W605 2 / E711 2 / F403 1 / **F821 1** / 残り F401/F841
- **重点**:
  - `scripts/detect_flaky.py:29` F821 `Undefined name 'e'`: **例外変数が束縛される前/別スコープで `e` を参照している実バグの疑い**。周辺コードを読み、`except ... as e` の漏れなら修正、到達不能コードなら削除。修正後、スクリプト自体の動作確認（`--help` または乾式実行）まで行う
  - E712/E711: `== True` / `== None` は SQLAlchemy の Column 比較では**正当**な場合がある（`Model.flag == True` は SQLAlchemy で必須の書き方）。対象が ORM フィルタなら `# noqa: E712` を付け、**理由コメント必須**。平文の真偽値比較のみ修正
  - F403（`tests/unit/test_book_score_service.py:6` の star import）: star import を明示 import に置換するか、必要なら per-file-ignore に登録（PLAN_R3 の erotic shim と同様の正当性が要る）
- **完了条件**: `ruff check src tests config scripts` → **0 errors**
- **コミット**: `style(q1): ruff 手動修正（F821 実バグ修正を含む 73 件）`

#### Step 12: baseline 更新 + README 同期

- **コマンド**:
  ```bash
  .venv/bin/python scripts/ci_lint_ratchet.py --tool ruff --update      # baseline を 0 へ
  .venv/bin/python scripts/ci_lint_ratchet.py --tool mypy --update      # baseline を実測（CI ピン版 mypy 2.3.1 での値）へ
  .venv/bin/python scripts/ci_lint_ratchet.py --tool format             # 0 維持
  ```
- **同コミットで必須**（P4）: `README.md` の静的解析ゲート注記の数値を `ruff=0 / mypy=<実測> / format=0` に更新。`config/ci_lint_baseline.json` の `history` に本日の実測と件数を追記
- **完了条件**:
  ```bash
  .venv/bin/python scripts/ci_lint_ratchet.py --tool all    # 3 tools とも exit 0
  python3 -c "import json; d=json.load(open('config/ci_lint_baseline.json')); print(d['ruff_errors'], d['mypy_errors'], d['format_files'])"   # 0 / 実測 / 0
  ```
- **設計メモ（P5）**: ratchet の「減少時自動引き下げ」は CI 上でコミットされず消失する。本 Step 以降は**減少を確認したら必ずローカル `--update` + コミット**を運用規約とする（docs/development_guide.md に追記、Step 15 で実施）
- **コミット**: `chore(q1): lint/mypy baseline を実測へ更新（ruff 170→0、mypy→実測）+ README 同期`

### Phase E: 再発防止のゲート化（Steps 13-16）

#### Step 13: xpassed 3 件の解消

- **コマンド**:
  ```bash
  .venv/bin/python -m pytest tests/unit -q -rX --timeout=120    # xpassed の一覧取得
  ```
- **変更**: 各テストを (a) xfail を外して正規テストに昇格、または (b) 本当に失敗するなら `xfail(strict=True)` にする。**理由をコメントで残す**
- **完了条件**: `-rX` で xpassed が 0 件
- **コミット**: `test(q1): xpassed 3 件を解消（xfail 解除 or strict 化）`

#### Step 14: ツールバージョンピン統一 + 契約テスト

- **対象**: `requirements.txt`、`.github/workflows/ci.yml`、`Makefile`
- **変更**:
  1. `requirements.txt` に `ruff==0.16.5` / `mypy==2.3.1` を CI と同一ピンで追加（`pyproject.toml` の dev は `>=` のまま、**ゲート用の正確なバージョンは requirements.txt が SSOT**）
  2. 新規回帰テスト `tests/regression/test_tool_version_parity.py`: `ci.yml` の `pip install "ruff==X" "mypy==Y"` を正規表現で抽出し、`requirements.txt` のバージョンと一致することを assert。**CI 側のピンが変わったら requirements も変える**ことを構造的に強制（mypy 2.3.1 と 2.4.1 で件数が 126 件ずれた実測が、このゲートの存在理由）
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_tool_version_parity.py -q   # 1 passed
  grep -E "ruff==|mypy==" requirements.txt                                      # CI と同一バージョン
  ```
- **コミット**: `feat(q1): lint ツールバージョンの CI/ローカル統一 + バージョン整合契約テスト`

#### Step 15: 運用ゲート（Makefile + ドキュメント）

- **対象**: `Makefile`、`docs/development_guide.md`、`docs/STATUS.md`
- **変更**:
  1. `Makefile` に `ci-parity` ターゲット追加（CI と同一コマンド列をローカルで再現する）:
     ```makefile
     ci-parity: ## CI と同一のコマンド列をローカル実行
     	$(PYTHON) scripts/ci_lint_ratchet.py --tool all
     	$(PYTHON) -m pytest -q -m "not integration and not perf and not slow" --timeout=120
     	cd frontend && npm run test:ci
     ```
  2. `docs/development_guide.md` に運用規約を追記:
     - 「main で unit suite が赤の状態で**新しい機能コミットを積まない**（赤は当該日中に解消）」
     - 「インターフェース（関数シグネチャ / ルート / モデル列）を変えたら、**同一コミット**で参照テストを更新する（P2）」
     - 「baseline が下がったらローカル `--update` で確定させる（CI 自動引き下げは消失する）」
  3. `docs/STATUS.md` §4 を 2026-11-15 実測値に更新（15 失敗 → 0/1、ruff 170 → 0、mypy 実測値、xpassed 0）
- **完了条件**: `make ci-parity` が exit 0（分類 C 1 件を除く。同 1 件は Q2 で解消）
- **コミット**: `docs(q1): 赤のまま放置禁止の運用規約 + make ci-parity 追加、STATUS 実測同期`

#### Step 16: 最終検証

- **コマンド**:
  ```bash
  git status --short                                            # clean
  make verify                                                    # lint → format-check → typecheck → test-unit → test-contract → test-migration
  .venv/bin/python scripts/ci_lint_ratchet.py --tool all        # 3 tools exit 0
  .venv/bin/python -m pytest tests/unit -q --timeout=120        # 1 failed（分類C・Q2対象）のみ
  ```
- **CI 確認**: push 後の GitHub Actions で `static-analysis` / `release-consistency` / `test` ジョブが緑であること（`integration` / `frontend` は既存の状態を確認し、赤なら本計画の外で起票）
- **コミット**: なし（検証のみ。問題があれば個別 fix コミット）

---

## 5. 回帰テスト一覧（本計画で新設・強化するもの）

| テスト | 種別 | 防ぐ再発 |
|---|---|---|
| `tests/regression/test_model_migration_parity.py`（新規, Step 3） | 構造ゲート | H12 型事故: マイグレーションと ORM の列乖離（両方向検出） |
| `tests/unit/llm/adapters/test_llm_adapters_extra.py` 追加（Step 8） | 仕様固定 | factory の `base_url` 単独指定バリデーションの緩和 |
| `tests/regression/test_tool_version_parity.py`（新規, Step 14） | 契約 | CI / ローカルの lint ツールバージョン乖離（2.3.1 と 2.4.1 で 126 件差の実測あり） |
| `tests/regression/` 既存 ratchet 系（維持） | 劣化検出 | ruff / mypy / format の再劣化（baseline 0 運用に移行） |
| H9 / H10 / H13 / C1 の各テスト更新（Steps 5-8） | 仕様固定 | 「テストだけ古い」状態の再来（P2 の規律とセット） |

---

## 6. リスクとロールバック

| リスク | 対策 |
|---|---|
| F401 自動削除で再エクスポートが壊れる | Step 10 で unit suite 全実行を必須化。壊れたら当該 import を戻し `__init__.py` の per-file-ignore が効いているか確認 |
| E712 の ORM 比較を誤って「修正」し意味を変える | SQLAlchemy Column 比較は `# noqa: E712` + 理由コメント。平文のみ修正 |
| mypy baseline 更新後に CI で件数がずれる | Step 14 のバージョンピン統一が前提。ピン変更時は baseline を再実測する運用を Step 15 で文書化 |
| 分類 C の 1 件が Q2 まで赤で残る | Step 14 の予算 JSON に「既知 1 件」として登録し、Q2 Step 8 で予算 0 化 |
| ロールバック | 1 Step = 1 コミットのため `git revert <step-commit>` で単位復帰可能 |

---

## 7. 完了の定義（Acceptance Criteria）

1. `pytest tests/unit -q --timeout=120` → failed 1 件以下（かつそれが分類 C = Q2 対象）
2. `scripts/ci_lint_ratchet.py --tool all` → exit 0、`ruff=0`
3. xpassed 0、`test_model_migration_parity.py` / `test_tool_version_parity.py` が常設ゲートとして動作
4. `docs/STATUS.md` が 2026-11-15 の実測値で更新されている
5. GitHub Actions の `static-analysis` / `release-consistency` / `test` が緑
