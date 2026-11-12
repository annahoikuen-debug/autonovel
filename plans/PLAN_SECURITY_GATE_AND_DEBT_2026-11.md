# PLAN: セキュリティゲート・技術負債の解消計画（2026-11-13 時点）

対象ブランチ: `feature/commercial-lp-phase1`（HEAD `43b12db2`、リモート同期済み）
前段: Phase R3 shim 削除 18 ステップ完了（`plans/PLAN_R3_SHIM_REMOVAL_18STEPS.md`）

---

## 1. 方針（判断基準）

この計画を通じて守る 5 原則:

| # | 原則 | 理由 |
|---|---|---|
| P1 | **ゲートは「実装で直す」を第一選択とし、allowlist は「理由 + TODO(H1-N)」を必須にする** | 既存 allowlist は目を閉じる場所として使われ、2026-10-03 監査で marketing/collab の IDOR を許した実績がある（`test_idor_regression.py:16-28` のコメント） |
| P2 | **既存失敗（base 由来）と新規回帰を分離して管理する** | base worktree（`/tmp/opencode/base_review`, `79b0d041`）との full run 比較が唯一の信頼できる判定。混ぜると「いつから壊れたか」が消える |
| P3 | **生成物は変更時に必ず再生成し差分を確認する** | `docs/openapi.json` / `frontend/src/types/api.generated.ts` / golden JSON / `var/import_graph.json`。未再生成は別ゲートで落ちる |
| P4 | **コミット前に並行セッションとの競合を検知する** | `git status` / `git log -3` / `tests/unit/config/test_public_api.py` を実行してから commit。前回の `43b12db2` は外部コミット `1d852094` の契約テストを壊した |
| P5 | **各 Phase は自分の検証コマンドが green になるまで次へ進まない** | 「動くはず」を確認しない |

---

## 2. Phase 0: ベースライン（現状整理）

### 2.1 確定している事実

| 項目 | 値 |
|---|---|
| HEAD | `43b12db2`（リモート同期） |
| collection error | **0 件**（10703 collected / 21.79s、予算 30s） |
| `tasks.py` の外部未コミット編集 | **破棄済み**（IndentationError 解消、`git status` クリーン） |
| shim 削除に起因する新規回帰 | **0 件**（前回レビューで全解消） |

### 2.2 失敗の分類（base full run 40 件 + 並行コミットによる変動）

| 区分 | 件数 | 内容 | 本計画の Phase |
|---|---|---|---|
| A. セキュリティゲート | 4 | IDOR 2（`admin_phase2`）+ route mount 2（`agent_memory`/`conflicts`/`dashboard`） | **Phase 1** |
| B. config 契約テスト | 1 | `test_config_keeps_critical_compat_names`（`43b12db2` が外部の再バインドを削除して regression） | **Phase 2（意思決定必須）** |
| C. DAG 所有権 | 設計課題 | `GET /api/tasks/dag/{dag_id}` に所有権・認証の限定が無い（ゲート未検出だがレビュー指摘） | **Phase 3** |
| D. バージョン整合 | 6〜8 | README / package.json / docker-compose.prod / openapi.json / STATUS.md が `7.0.0` 未追従 + `test_pyproject_version_is_v6` のハードコード | **Phase 4** |
| E. lint/ruff 負債 | 4 | lint budget 149/予算122・F821・LLM ruff・env var hygiene | **Phase 5** |
| F. e2e / perf / その他 | 10+ | e2e 5・perf 8・conftest/encoding/t6/db ほか | **Phase 6（調査後、別計画）** |

> Phase 0 の数値は全件テスト実行の完了後に確定し、この表を更新する。

---

## 3. Phase 1: セキュリティゲート 4 件

### 3-1. IDOR: `admin_phase2.py::get_reflection_stats`

**事実**
- `src/backend/routers/admin_phase2.py:226` `get_reflection_stats(book_id)` が `OWNERSHIP_MARKERS` を呼ばない
- ただし `rag_router` は router レベルで `dependencies=[Depends(require_api_key)]`（`admin_phase2.py:157-161`）＝認証済み
- 返り値は**ハードコードされたゼロのスタブ**（`total_calls=0` 等、実データを返さない）
- 呼び出し元はフロント無し。`frontend/src/types/api.generated.ts`（生成物）のみ

**方針: allowlist 追加（P1 適用 — 理由付き）**
`NO_OWNERSHIP_NEEDED` に `admin_phase2` を追加し、以下をコメントで明記する:

```
# admin_phase2: /admin/rag/reflection_stats のみ book_id を受け取るが、
#   (1) router レベルの require_api_key で認証済み（API Key は
#       require_admin_user_or_key 経由で api_readonly ロール＝読み取り専用）
#   (2) 返り値は集計スタブで本文・設定を返さない
#   (3) ユーザーではなくサービス（API Key）が呼ぶ管理エンドポイント
#   のため、per-book 所有権ガードは適用しない。
# TODO(H1-2): スタブ削除の要否を判断し、削除するなら本エントリも除去すること。
```

**代替案（次点）**: スタブ自体を削除。ただし `docs/openapi.json` と
`api.generated.ts` の再生成が必要（P3）。Phase 6 で判断する。

### 3-2. IDOR: `AUTH_MARKERS` が `require_api_key` を認識しない

**事実**
- `tests/security/test_idor_regression.py:75` `AUTH_MARKERS = ("get_current_user", "enforce_book_ownership", "requires_book_ownership")`
- `admin_phase2.py` は router レベルの `require_api_key` のみ → フラグ
- `require_api_key`（`src/backend/auth.py:99`）は実際に401 を返す本物の認証依存

**方針: テスト側を直す（実装側を変えない）**
`AUTH_MARKERS` に `"require_api_key"` と `"require_admin_user_or_key"` を追加する。

- 改悪の有無: 認証要件を「緩めた」のではなく「正しく認識した」だけ。
  `require_api_key` なしで `book_id` を扱う router は従来どおり赤
- 追加後、`admin_phase2` が消えることを確認

### 3-3. route mount parity: `agent_memory` / `conflicts` / `dashboard`

**事実（3 router 共通）**
- `src/backend/wiring.py` の `RouterMount` 一覧に**無い**（`server.py` ではなく `wiring.py` が登録元）
- **一度もマウントされた履歴が無い**（`git log -S agent_memory -- wiring/server/app_factory` が空）
- フロントからの参照**なし**（404 リスクなし）
- **認証依存が一切無い**（`Depends` 0 件）→ マウントすると未認証エンドポイントになる
- ユニット/統合テストは `src/api/*.py` の再エクスポート経由で直接 import して検証済み

**方針: `ALLOWLIST` に明記（P1 適用 — 理由付き）**
```python
# 一度もマウントされておらず、フロントからも参照されない（404 リスクなし）。
# 認証依存が無いためマウントすると未認証エンドポイントになる。
# 検証は tests/integration/api/test_{agent_memory_api,conflict_resolution,dashboard}.py
# が src/api/*.py の再エクスポート経由で直接実施している。
# TODO(H1-2): マウントして認証を付けるか、削除するかを判断する。
ALLOWLIST = {"metrics", "agent_memory", "conflicts", "dashboard"}
```

**代替案（次点）**: 削除（`src/backend/routers/*.py` 3 件 + `src/api/*.py` 3 件 +
統合テスト 3 件）。マウント履歴が無くフロント未使用なので本質的には死にコードだが、
削除はテストも消えるため影響が広く、Phase 6 の判断事項とする。

**やらないこと**: マウントする。認証が無いため（未認証エンドポイントの公開）。

### Phase 1 検証
```bash
.venv/bin/python -m pytest tests/security/ -q -p no:cacheprovider
# 期待: security配下 green（route mount 2 + IDOR 2 が消える）
.venv/bin/python -m ruff check tests/security/test_idor_regression.py tests/security/test_server_route_mount_parity.py
```

---

## 4. Phase 2: `config` 契約テストとの競合（**意思決定が必要**）

### 4.1 経緯（三方の主張）

| 時点 | commit | 内容 |
|---|---|---|
| 外部 | `0576a8f9` | `config/__init__.py` に `constants` / `FORBIDDEN_*` / `project_context` の再バインドを**追加**（+15） |
| 外部 | `1d852094` | その 4 名前が `__all__` に在ることを**契約テストで固定**（`tests/unit/config/test_public_api.py::test_config_keeps_critical_compat_names`） |
| 当方 | `43b12db2` | 再バインドを**削除**（-15、shim 的挙動の是正）＋呼び出し側を新パスへ移行 |

**結果: `test_config_keeps_critical_compat_names` が fail（現在 HEAD の唯一の自前回帰）。**

### 4.2 3 案

| 案 | 内容 | 長所 | 短所 |
|---|---|---|---|
| **A（推奨）** | `config/__init__.py` に PEP 562 の `__getattr__` を実装し、4 名前を**遅延解決 + `DeprecationWarning`** で提供 | 契約テストは `hasattr()` が True になり**両立**。import 時のコスト増なし。旧呼び出し側は警告付きで動作＝移行猶予。`import config.constants` は従来どおり `ModuleNotFoundError`（shim 削除の成果は維持） | `config.X` 属性は依然として解決できる（表面的な互換は残る） |
| B | 再バインドを復元（外部の意図に従う） | 最も単純 | shim 的挙動の完全復帰。当方の Phase R3 の是正が無意味になる |
| C | 契約テスト側を修正（`critical` から4名前を外す） | 厳格で一貫 | **外部が意図的に書いたテストを当方の都合で書き換える**（P4 違反気味）。外部セッションとの対立リスク |

### 4.3 案 A の実装概要

```python
# config/__init__.py 末尾
def __getattr__(name: str):
    """後方互換の遅延解決（Phase R3: 旧パスからの移行猶予）。"""
    import warnings
    compat = {
        "constants": "src.config.constants",
        "FORBIDDEN_SUMMARY_PATTERNS": "src.domain.styles",
        "FORBIDDEN_WORD_REPLACEMENTS": "src.domain.styles",
        "project_context": "src.infrastructure.config.project_context",
    }
    if name in compat:
        warnings.warn(
            f"config.{name} は非推奨。{compat[name]} を直接 import してください",
            DeprecationWarning, stacklevel=2,
        )
        import importlib
        return importlib.import_module(compat[name]) if name in ("constants", "project_context") \
            else getattr(importlib.import_module(compat[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**注意点（実装時に検証）**
- `from config import constants` が PEP 562 で解決されること（`from ... import` は `getattr` を経由）
- `importlib.import_module("config.constants")` が従来どおり `ModuleNotFoundError`
  （`test_removed_shim_import_fails` が緑のまま）
- `tests/unit/story_spine/test_removed_definitions.py`（`assert not hasattr(config, "PLOT_STRUCTURES")`）が緑のまま

**検証**
```bash
.venv/bin/python -m pytest tests/unit/config/ tests/regression/test_shim_removal_detection.py -q -p no:cacheprovider
```

---

## 5. Phase 3: DAG ステータスの所有権

### 5.1 事実

- `GET /api/tasks/dag/{dag_id}`（`tasks.py:83`）は所有権チェックが無く、router の `get_current_user` 認証のみ
- `DAGGraph`（`dag_models.py:40`）は `dag_id` と `nodes` のみで **owner / book_id フィールドが無い**
- checkpoint は **`/tmp/dag_checkpoints`** に JSON 保存（`dag_persistence.py:37`）
- `dag_id` は 2 形式: `novel_b{book_id}_ep{ep_num}` / `orch_{correlation_id}` → **全てから book を導出できない**
- フロントからの参照**なし**（生成型定義のみ）
- `dag_status:*` の Redis キーは**誰も書かない**（読み取り専用のデッドパス）
- リポジトリには既に「管理用エンドポイントは admin/API Key で守る」先例がある
  （`get_wal_logs`: 「WAL には入力/出力ペイロードが含まれるため、管理者権限または API Key を要求する」）

### 5.2 方針: **まず認証を限定し、owner 付与は設計フェーズに分離**

| 案 | 内容 | 評価 |
|---|---|---|
| **A（推奨）** | `get_dag_status` に `dependencies=[Depends(require_admin_user_or_key)]` を追加 | **小変更で実効**。フロント未使用なので利便性低下なし。WAL エンドポイントと同一パターン。checkpoint に owner が無い設計問題は先送りできる |
| B | `DAGGraph` に `owner_id` を追加し checkpoint に永続化、読み取り時に照合 | 正解だが設計が必要（作成経路に user を渡す・旧 checkpoint の扱い＝fail-open/closed・`orch_*` の扱い）。**Phase 3b として別途スパイク** |
| C | `dag_id` から `book_id` を正規表現で導出 | `orch_*` で破綻。**不採用** |
| D | エンドポイント削除 | フロント未使用だが、運用デバッグ用途の可能性あり。**削除は Phase 6** |

**Phase 3 の成果物**: 案 A の実装 + 案 B の設計メモ（`docs/` か本計画の追記）

**検証**
```bash
.venv/bin/python -m pytest tests/unit/test_p4_async_and_db_concurrency.py tests/security/ -q -p no:cacheprovider
```

---

## 6. Phase 4: バージョン `7.0.0` への一括同期

`pyproject.toml` / `src/backend/__init__.py` / `src/cli/main.py` は既に `7.0.0`
（外部コミット `0576a8f9`）。残りの SSOT 適用先を揃える:

| 対象 | 状態 | 手順 |
|---|---|---|
| `README.md` | バッジ・リリースタグが旧版 | `version-{X}-brightgreen` / `releases/tag/v{X}` を 7.0.0 に |
| `frontend/package.json` | `version` が旧版 | 7.0.0 |
| `docker-compose.prod.yml` | `image: autonovel-*:{X}` タグ | 7.0.0 |
| `docs/openapi.json` | `version` フィールド | 生成し直し（P3） |
| `docs/STATUS.md` | バージョン節 | 7.0.0 |
| `tests/regression/test_v6_version_consistency.py::test_pyproject_version_is_v6` | `== "6.0.0"` のハードコード | **テスト自体が古い**。SSOT 一致チェックに書き換える（`test_changelog_top_entry_matches_pyproject` は既に SSOT 方式） |

**検証**
```bash
.venv/bin/python -m pytest tests/regression/test_v5_version_consistency.py \
  tests/regression/test_v6_version_consistency.py \
  tests/regression/test_docs_numbers_consistency.py \
  tests/regression/test_docs_router_count_matches_reality.py \
  tests/regression/test_status_doc_has_effect_measurement.py \
  tests/unit/cli/test_cli_main.py -q -p no:cacheprovider
```

---

## 7. Phase 5: lint / ruff 負債

| 対象 | 状態 | 手順 |
|---|---|---|
| `test_lint_error_count_within_budget` | `src tests` 149 vs `LINT_ERROR_BUDGET = 122`（base 時点から超過） | 削減して予算を下げる（**機械削除禁止** — `src/narrative_balancer` の再エクスポート破壊実績あり）。F401 の「意図的な再エクスポート」は `# noqa` で明示化する |
| `test_ruff_reports_no_f821` / `test_ruff_clean_llm` | F821 2件・LLM 系 ruff | 該当箇所を個別修正 |
| `test_no_new_env_direct_assignment_without_monkeypatch` | `tests/` 配下の環境変数直接代入が許可外 | `monkeypatch.setenv` 化、または `ALLOWED_FILES` に理由付きで追加 |

**検証**: 該当 4 テスト + `ruff check src tests`

---

## 8. Phase 6: e2e / perf / その他（**調査してから別計画**）

対象（base 由来のまま残っているもの）:

- e2e: `test_coarse_fine_e2e` / `test_pillar1_pipeline_e2e` / `test_production_e2e`（FileNotFound）/ `test_regeneration_loop_e2e` / `test_pdca_pipeline_integration`
- perf: `test_performance_regression` 6件 / `test_dsp_perf` / `test_fusion_perf` / `test_v6_llm_call_budget`
- その他: `test_conftest_mock_llm_adapter_fixture` / `test_subprocess_encoding_gate` / `test_t6_plan_completion` / `test_book_repository_concurrency` / `test_get_db_manager_singleton`（**既知の flaky**、`var/reports/qa_baseline_failures.txt` 記載）

**方針**: これらは環境依存・閾値・古い計画書の可能性が高く、根治の前に
「実測 → 原因分類（本物の欠陥 / 閾値 / flaky / 計画書の陳腐化）」を個別に行う。
本計画には含めず、Phase 6 の調査結果から別計画を起こす。

---

## 9. 実行順序と完了条件

| Phase | 内容 | 完了条件（検証コマンド green） | 想定サイズ |
|---|---|---|---|
| 0 | ベースライン確定（全件テスト） | 失敗一覧の分類表を本計画に反映 | 実行中 |
| 1 | セキュリティ 4 件 | `pytest tests/security/` green | 小 |
| 2 | config 契約競合（案 A） | `pytest tests/unit/config/ tests/regression/test_shim_removal_detection.py` green | 小 |
| 3 | DAG 認証限定 + 設計メモ | `pytest tests/unit/test_p4_async_and_db_concurrency.py tests/security/` green | 小 |
| 4 | バージョン同期 | version 系 6 ファイル green | 中（生成物再生成あり） |
| 5 | lint 負債 | lint 系 4 green + `ruff check src tests` | 中（判断を要する） |
| 6 | e2e/perf 調査 | 調査結果 → 別計画 | 大（本計画の範囲外） |

**全フェーズ共通の完了条件（P4）**
1. `git status` が意図した変更のみ
2. `git log -3` で並行コミットが入っていないこと
3. `pytest tests/unit/config/test_public_api.py` green（Phase 2 以降）
4. full run で「base 由来の失敗以外」が **0 件**
5. コミット → プッシュ

---

## 10. リスク

| リスク | 対策 |
|---|---|
| 並行セッションが同じファイルを編集（前回 `tasks.py` / `config/__init__.py` で発生） | P4 のチェックをコミット直前に毎回実行。衝突したら**当方の変更を破棄して外部に合わせる**（外部が契約テストを持つ場合） |
| allowlist 追加が IDOR の目を閉じる | P1: 理由 + TODO(H1-N) 必須。Phase 6 の調査で「実装して外す」を判断 |
| lint の機械削除が再エクスポートを壊す | `F401` は手動判断 + `# noqa`。`REEXPORT_SENTINEL = "src/narrative_balancer"` を守る |
| 生成物の未再生成 | P3: 変更後 `scripts/generate_ts_types.py` 等を実行し diff を確認 |
| full run の collection speed ゲートが負荷で揺れる | 測定は 3 回実行して中央値。他テストと並列実行しない |
