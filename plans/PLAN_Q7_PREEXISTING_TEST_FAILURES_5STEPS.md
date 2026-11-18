# PLAN_Q7: base 由来の pre-existing テスト失敗 19 件の原因究明と修正計画 (5 STEPS)

> **目的**: `fix/q1-red-gate-recovery` ブランチ（HEAD `88b4a034`、Plan Q6 完了後）における、
> base `68137ce5` から継承する pre-existing テスト失敗 19 件の原因究明と修正計画を策定する。
> **本計画の特徴**:
> 1. **全件について base でも同一失敗を実測で確認済み**（本差分による回帰は 0 件）。
> 2. Plan Q6 のスコープ外として切り出した項目。ユーザーの判断に基づき修正対象を選定する。
> 3. 修正可能なものは個別にステップを設け、修正困難・外部依存のものは「調査・報告」にとどめる。
>
> **対象ブランチ**: `fix/q1-red-gate-recovery`（HEAD `88b4a034`、ワークツリークリーン）
> **前提**: `PLAN_Q6_REVIEW_FINDINGS_FIXES_12STEPS.md` が完了済み（12 コミット）。
> **作業方針**: 1 ステップ = 1 コミット。base worktree `68137ce5` での事前再現を必須とし、
> 「base でも失敗」であることを証拠として記録する。
>
> **実測根拠（フルスイート、`not integration and not perf and not slow`）**:
> | 環境 | failed | passed | 備考 |
> |---|---|---|---|
> | base `68137ce5` | **23** | 9292 | Plan Q6 前の基線 |
> | HEAD `88b4a034` (Q6 完了後) | **19** | 9303 | Plan Q6 完了後。4 件解消、新規回帰 0 |
>
> - HEAD の失敗 19 件は**すべて base でも失敗**（pre-existing、本差分の回帰なし）。
> - Plan Q6 で解消済み 4 件: `test_H1_lint_ratchet` / `test_old_llm_shim_paths_removed` /
>   `test_shim_imports` (`src.api.health`, `src.services.llm.circuit_breaker`)。

---

## 0. 対象テスト一覧（19 件）

| # | テスト ID | フェーズ | base での再現 | 想定原因系統 |
|---|---|---|---|---|
| 1 | `tests/api/test_real_easy_mode_api.py::test_easy_mode_generate_enqueues_task` | A | ○ | easy_mode API（タスクエンキュー） |
| 2 | `tests/security/test_easy_mode_export_with_data_ownership.py::test_export_with_data_rejects_unauthenticated_when_dependency_added` | A | ○ | セキュリティ export（認証） |
| 3 | `tests/security/test_easy_mode_export_with_data_ownership.py::test_export_with_data_rejects_cross_tenant` | A | ○ | セキュリティ export（クロステナント） |
| 4 | `tests/e2e/test_production_e2e.py::test_full_generation_flow` | B | ○ | e2e（FileNotFound） |
| 5 | `tests/e2e/test_spine_end_to_end.py::test_card_to_spine_to_prompt` | B | ○ | e2e（ModuleNotFound） |
| 6 | `tests/e2e/test_spine_end_to_end.py::test_off_quality_produces_byte_identical_prompt` | B | ○ | e2e（ModuleNotFound） |
| 7 | `tests/e2e/test_spine_end_to_end.py::test_soft_and_hard_differ` | B | ○ | e2e（ModuleNotFound） |
| 8 | `tests/e2e/test_spine_end_to_end.py::test_spine_never_costs_llm_calls_end_to_end` | B | ○ | e2e（ModuleNotFound） |
| 9 | `tests/e2e/test_v5_workflow_e2e.py::test_full_creation_to_zip_delivery_flow` | B | ○ | e2e（zip 配信フロー） |
| 10 | `tests/perf/test_v6_llm_call_budget.py::TestLlmCallsPerEpisode::test_real_audit_phase_call_count_is_measured` | C | ○ | perf（フルスイート時のみ失敗、単体 green） |
| 11 | `tests/performance/test_fusion_perf.py::test_fusion_performance_100_pairs` | C | ○ | performance（100 ペア） |
| 12 | `tests/regression/test_H1_no_orphan_shims.py::test_no_new_orphan_shim_in_services` | D | ○ | regression（orphan shim） |
| 13 | `tests/regression/test_H1_no_orphan_shims.py::test_known_orphans_still_exist` | D | ○ | regression（KNOWN_ORPHANS 残骸 45 件） |
| 14 | `tests/regression/test_shim_usage_stats.py::test_report_shim_usage_stats` | D | ○ | regression（shim 使用統計） |
| 15 | `tests/regression/test_t6_plan_completion.py::test_t6_plan_all_steps_satisfied` | D | ○ | regression（t6 計画完了） |
| 16 | `tests/regression/test_tenant_fk_integrity.py::test_alembic_has_single_head` | D | ○ | regression（alembic head: 0035 期待 vs 0036 実） |
| 17 | `tests/regression/test_long_form_fact_retention.py::TestFactRetention::test_rollup_off_hierarchical_returns_empty` | D | ○ | regression（long form fact retention） |
| 18 | `tests/regression/test_long_form_fact_retention.py::TestFactRetention::test_rollup_on_fact_is_retained` | D | ○ | regression（long form fact retention） |
| 19 | `tests/unit/backend/test_backend_database_core.py::test_get_db_manager_singleton` | E | ○ | unit（フルスイート時のみ失敗、単体 green） |

> 注意: #10 と #19 は**フルスイート実行時にのみ失敗し、単体実行では green**。テスト順序依存の可能性があり、
> 個別デバッグが必要。

---

## 1. 作業方針（判断基準）

| # | 原則 | 理由 |
|---|---|---|
| P1 | **base でも同一失敗を実測で確認したもののみを対象とする** | Plan Q6 の P3 原則を継承。本差分に起因しない赤を誤って修正しない |
| P2 | **修正可能なものは個別ステップで、困難・外部依存のものは「調査報告」にとどめる** | 全件を強制修正するとスコープが肥大化し、Plan Q6 のマージを遅延させる |
| P3 | **テスト順序依存（単体 green / フルスイート red）は別途切り分ける** | #10 / #19 のように環境・順序に依存する失敗は、修正アプローチが異なる |

---

## Phase A: 認証・データ所有権系（3 件）

### Step 1: `tests/api/test_real_easy_mode_api.py` とセキュリティ export 2 件の原因究明

**対象**:
- `tests/api/test_real_easy_mode_api.py::test_easy_mode_generate_enqueues_task`
- `tests/security/test_easy_mode_export_with_data_ownership.py::test_export_with_data_rejects_unauthenticated_when_dependency_added`
- `tests/security/test_easy_mode_export_with_data_ownership.py::test_export_with_data_rejects_cross_tenant`

**変更**:
1. 各テストを単体実行し、失敗の再現とエラー詳細を記録する。
2. `config/settings.toml` 欠如や `src.services.llm.prompts` などのモジュール欠落が関与しているか確認する
   （Plan Q6 Step3 で settings.toml フォールバックを導入したが、e2e/security テストでは別経路で失敗する可能性）。
3. 原因が特定できれば修正を実装、特定できなければ「調査報告」として本計画に記録する。

**検証**:
```bash
.venv/bin/python -m pytest tests/api/test_real_easy_mode_api.py::test_easy_mode_generate_enqueues_task \
  tests/security/test_easy_mode_export_with_data_ownership.py -q --timeout=120
```
**受け入れ基準**: 各テストの失敗原因が特定され、修正または「調査報告」が本計画に記録される。

---

## Phase B: e2e 系（6 件）

### Step 2: e2e テスト 6 件の原因究明と修正

**対象**:
- `tests/e2e/test_production_e2e.py::test_full_generation_flow`（FileNotFound）
- `tests/e2e/test_spine_end_to_end.py` ×4（ModuleNotFound）
- `tests/e2e/test_v5_workflow_e2e.py::test_full_creation_to_zip_delivery_flow`

**変更**:
1. 各テストを単体実行し、エラー詳細（FileNotFound / ModuleNotFound の対象モジュール）を記録する。
2. 欠落モジュールが `git ls-files` で 0 件（追跡外）であるか確認する。
3. 追跡外モジュールへの依存がテストコード側にある場合、テスト側のモック化またはスキップを検討する。
4. 本番コード側の未実装モジュールに起因する場合は、別実装計画へエスカレートする。

**検証**:
```bash
.venv/bin/python -m pytest tests/e2e/test_production_e2e.py tests/e2e/test_spine_end_to_end.py \
  tests/e2e/test_v5_workflow_e2e.py -q --timeout=120
```
**受け入れ基準**: 各テストの失敗原因が特定され、修正または「調査報告」が本計画に記録される。

---

## Phase C: perf / performance 系（2 件）

### Step 3: perf / performance テスト 2 件の原因究明

**対象**:
- `tests/perf/test_v6_llm_call_budget.py::TestLlmCallsPerEpisode::test_real_audit_phase_call_count_is_measured`
- `tests/performance/test_fusion_perf.py::test_fusion_performance_100_pairs`

**変更**:
1. 各テストを単体実行し、green であることを確認する（フルスイート時のみ失敗の順序依存疑い）。
2. フルスイート実行時にのみ失敗する場合、テスト間の状態汚染（DB セッション、モック、環境変数）を調査する。
3. 必要に応じてテスト分離（fixture のスコープ見直し、モジュール直下 import の回避など）を実装する。

**検証**:
```bash
.venv/bin/python -m pytest tests/perf/test_v6_llm_call_budget.py::TestLlmCallsPerEpisode::test_real_audit_phase_call_count_is_measured \
  tests/performance/test_fusion_perf.py::test_fusion_performance_100_pairs -q --timeout=120
.venv/bin/python -m pytest -q -m "not integration and not perf and not slow" -p no:randomly --timeout=120 \
  tests/perf/test_v6_llm_call_budget.py tests/performance/test_fusion_perf.py 2>&1 | tail -5
```
**受け入れ基準**: 単体実行で green、または順序依存の原因が特定され修正される。

---

## Phase D: regression 系（7 件）

### Step 4: regression テスト 7 件の原因究明と修正

**対象**:
- `tests/regression/test_H1_no_orphan_shims.py` ×2（orphan shim / KNOWN_ORPHANS 残骸）
- `tests/regression/test_shim_usage_stats.py::test_report_shim_usage_stats`
- `tests/regression/test_t6_plan_completion.py::test_t6_plan_all_steps_satisfied`
- `tests/regression/test_tenant_fk_integrity.py::test_alembic_has_single_head`（alembic head: 0035 期待 vs 0036 実）
- `tests/regression/test_long_form_fact_retention.py` ×2（fact retention rollup）

**変更**:
1. 各テストを単体実行し、エラー詳細を記録する。
2. `KNOWN_ORPHANS` 46 件のうち 45 件が削除済み shim 残骸であること（Plan Q5 D-3 記録済み）を確認し、
   `test_known_orphans_still_exist` の対応方針（別計画 `PLAN_R3_SHIM_REMOVAL_18STEPS.md` へ接続）を確認する。
3. alembic head の不一致（0035 vs 0036）はマイグレーションファイルの整合性確認が必要。
4. long_form fact retention の NOT NULL 失敗は DB スキーマとテストデータの整合性確認が必要。

**検証**:
```bash
.venv/bin/python -m pytest tests/regression/test_H1_no_orphan_shims.py \
  tests/regression/test_shim_usage_stats.py tests/regression/test_t6_plan_completion.py \
  tests/regression/test_tenant_fk_integrity.py tests/regression/test_long_form_fact_retention.py \
  -q --timeout=120
```
**受け入れ基準**: 各テストの失敗原因が特定され、修正または「別計画へのエスカレート」が記録される。

---

## Phase E: unit backend 系（1 件）

### Step 5: `test_get_db_manager_singleton` の原因究明

**対象**:
- `tests/unit/backend/test_backend_database_core.py::test_get_db_manager_singleton`

**変更**:
1. 単体実行では green であることを再確認する。
2. フルスイート実行時にのみ失敗する原因（他テストによるグローバル状態の汚染、シングルトンインスタンスの使い回しなど）を調査する。
3. 原因が特定できればテスト分離またはグローバル状態のリセットを実装する。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/backend/test_backend_database_core.py::test_get_db_manager_singleton -q --timeout=120
```
**受け入れ基準**: 単体実行で green、または順序依存の原因が特定される。

---

## 最終ゲート

```bash
# Plan Q6 の全ゲートが green であることを再確認
.venv/bin/ruff check src tests config scripts
.venv/bin/python scripts/ci_lint_ratchet.py --tool all
.venv/bin/python scripts/check_test_collection.py
.venv/bin/python scripts/check_untracked_imports.py --strict

# Plan Q7 対象 19 件の単体実行（base でも失敗することを再確認）
.venv/bin/python -m pytest <19 件のテスト ID> -q --timeout=120

# フルスイートで回帰なし（failed が 19 件を超えない）
.venv/bin/python -m pytest -q -m "not integration and not perf and not slow" -p no:randomly --timeout=120
```

**受け入れ基準**:
1. Plan Q6 の全ゲートが green（Plan Q7 の作業で劣化させない）。
2. Plan Q7 対象 19 件の失敗原因がすべて特定される。
3. 修正対象と判断したテストが green になる。
4. 修正困難・外部依存のものは「調査報告」として本計画または別計画に記録される。
5. フルスイートの failed が 19 件を超えない（本計画による回帰なし）。

---

## リスク

| リスク | 影響 | 緩和 |
|---|---|---|
| e2e / perf テストは外部依存（DB / LLM / ネットワーク）が強く、ローカル再現が困難 | 原因究明に時間がかかる | 単体実行で green か確認し、フルスイート時のみ失敗するものは順序依存として切り分ける |
| KNOWN_ORPHANS 45 件の shim 残骸は別計画 `PLAN_R3_SHIM_REMOVAL_18STEPS.md` の管轄 | 本計画では修正不可 | 該当テストは「別計画へエスカレート」として記録 |
| alembic head 不一致（0035 vs 0036）はマイグレーションファイルの整合性問題 | マイグレーション関連のため慎重な対応が必要 | 別ステップでマイグレーションファイルを確認し、必要に応じて別計画へ |
| テスト順序依存（#10 / #19）は再現が不安定 | 修正が困難 | CI での再現性を重視し、テスト分離を最小限に抑える |

---

## スコープ外・別計画へ

| 項目 | 理由 | 接続先 |
|---|---|---|
| `test_known_orphans_still_exist`（KNOWN_ORPHANS 45 件の shim 残骸） | shim 削除に関連し、Plan Q7 の範囲を超える | `PLAN_R3_SHIM_REMOVAL_18STEPS.md` |
| alembic head 不一致の根本修正 | マイグレーションファイルの変更を伴う | 別マイグレーション計画 |
| CI（GitHub Actions）での e2e / perf テスト再現 | 外部依存（DB / LLM / ネットワーク） | CI 環境での個別調査 |
| Plan Q6 で既に解消済み 4 件 | 本計画の対象外（既に green） | — |
