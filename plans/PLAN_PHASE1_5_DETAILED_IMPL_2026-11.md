# 詳細実装計画書: Phase 1〜5（セキュリティゲート・config 衝突・DAG・バージョン・lint）

親計画: `plans/PLAN_SECURITY_GATE_AND_DEBT_2026-11.md`（方針 5 原則 P1〜P5 はこちら）
起点: HEAD `43b12db2` / ブランチ `feature/commercial-lp-phase1`
作成: 2026-11-13（Phase 0 全件テスト完了後）

本書は「何を・どのファイルの何行目で・どう変えるか・何で検証するか」を確定させた
**実行可能な手順書**である。方針の根拠は親計画を参照。

---

## 0. 実行順序とコミット構成

優先度順に **Phase 1 → 2 → 3 → 4 → 5**。各 Phase は自分の検証コマンドが
green になるまで次へ進まない（P5）。

| # | コミット | 内容 | 検証（green で次へ） |
|---|---|---|---|
| C1 | `Phase 1` | セキュリティゲート 4 件（**実装済み・検証済み**） | `pytest tests/security/` + ruff |
| C2 | `Phase 2` | config PEP 562 遅延解決 | `pytest tests/unit/config/ tests/unit/services/test_pipeline_steps_extended.py tests/regression/test_shim_removal_detection.py tests/unit/story_spine/test_removed_definitions.py` |
| C3 | `Phase 3` | `get_dag_status` を admin/API Key 限定 | `pytest tests/unit/test_dag_scheduler_part5_advanced.py tests/unit/test_p4_async_and_db_concurrency.py tests/security/` |
| C4 | `Phase 4` | バージョン 7.0.0 同期 + 生成物再生成 | version 系 6 テスト + 生成物整合 |
| C5 | `Phase 5` | lint 148→≤122 / F821 / env hygiene | lint 系 4 + `ruff check src tests` |
| C6 | 最終 | full run「base 由来以外 0」→ P4 チェック → プッシュ | full run 19 分 |

> コミットは Phase ごとに分ける（レビュー容易性・ロールバック容易性のため）。
> **各コミット直前に P4 チェックリスト（§10）を必ず実行する。**

---

## 1. Phase 0: ベースライン確定結果（完了）

全件テスト: `10337 passed / 40 failed / 2 errors / 319 skipped`（1144.90s = 19:04）
出典: 本リポジトリ HEAD の full run と `/tmp/base_full_failed.txt`（base `79b0d041`）の突合。

### 1.1 分類表

| 区分 | 件数 | 内容 | 扱い |
|---|---|---|---|
| **新規（自前回帰）** | **1** | `tests/unit/config/test_public_api.py::test_config_keeps_critical_compat_names` | **Phase 2** |
| **新規（自前回帰）** | **4** | `tests/unit/services/test_pipeline_steps_extended.py` ×4 — 全て `AttributeError: module 'config' has no attribute 'project_context'` | **Phase 2**（同一原因） |
| **新規（環境依存）** | **1** | `tests/performance/test_compression_benchmark.py::test_no_performance_regression` | Phase 6（§8） |
| base 由来 → **Phase 1 で解消** | 4 | `test_idor_regression` ×2 / `test_server_route_mount_parity` ×2 | **完了（C1）** |
| base 由来 → **Phase 4 で解消** | 8 | `v5::test_frontend_package_json_version` / `v5::test_prod_compose_image_tags` / `v5::test_readme_version_matches` / `v6::test_pyproject_version_is_v6` / `v6::test_readme_badge_matches_pyproject` / `docs_numbers::test_readme_version_matches_pyproject` / `docs_router_count::test_openapi_json_version_matches_pyproject` / `status_doc::test_version_section_matches_pyproject` | **Phase 4** |
| base 由来 → **Phase 5 で解消** | 4 | `test_lint_error_count_within_budget` / `test_ruff_clean_llm` / `test_ruff_reports_no_f821` / `test_no_new_env_direct_assignment_without_monkeypatch` | **Phase 5** |
| base 由来で**解消済み**（外部コミット `0576a8f9`） | 4 | `v5::test_backend_init_version` / `v5::test_cli_version` / `test_env_example_loads` / `cli::test_version_constant` | 対象外 |
| base 由来で **ERROR へ移行** | 2 | `perf::test_pgvector_{ingest,search}_1000_docs_performance`（FK 制約） | Phase 6 |
| **残存（Phase 6）** | 18 | e2e 5 / perf 6 / performance 2 / `test_conftest_mock_llm_adapter_fixture` / `docs_numbers::test_readme_llm_calls` / `test_subprocess_encoding_gate` / `test_t6_plan_completion` / `test_pdca_pipeline_integration` / `test_book_repository_concurrency` / `test_get_db_manager_singleton`（既知 flaky） | Phase 6（範囲外） |

**目標: Phase 1〜5 完了後、上記「新規 + Phase 対象」18 件が消え、
full run の失敗は「Phase 6 の base 由来 18 件 + 環境依存 1 件」のみになる。**

### 1.2 Phase 0 後片付け（実行済み）

- `tests/benchmarks/compression_baseline.json` のテスト副作用を `git checkout --` で revert 済み。
- `git status` は計画書のみ untracked（`plans/PLAN_SECURITY_GATE_AND_DEBT_2026-11.md`）。

---

## 2. Phase 1: セキュリティゲート 4 件 — **実装済み・検証済み（C1）**

### 2-1. `tests/security/test_idor_regression.py`

**(a) `NO_OWNERSHIP_NEEDED`（:16 の set）に `admin_phase2` を追加**

`test_no_router_exposes_book_id_without_ownership_check` の offenders は
`src/backend/routers/admin_phase2.py:226 get_reflection_stats` **のみ**（実測）。
追加したコメントの要点（P1: 理由 + TODO 必須）:

```python
    # admin_phase2: book_id を受けるのは `/admin/rag/reflection_stats`
    #   (admin_phase2.py:226) の 1 ハンドラだけで、
    #   (1) router レベルの `dependencies=[Depends(require_api_key)]`
    #       (admin_phase2.py:157-161) で API Key 認証を通過する
    #   (2) 返り値は `total_calls=0` 等の**ハードコードされた集計スタブ**で、
    #       本文・設定・プロット等の所有権対象データを一切返さない
    #   (3) ユーザーではなくサービス（API Key）が呼ぶ管理用エンドポイントで、
    #       フロントからも参照されない（生成物 api.generated.ts のみ）
    #   ため、per-book 所有権ガードは適用しない。
    # TODO(H1-2): このスタブが実データを返すようにする／削除するなら、
    #   本エントリも同時に削除すること（openapi.json と api.generated.ts の再生成を伴う）。
    "admin_phase2",
```

**(b) `AUTH_MARKERS`（:75）に本物の認証依存を追加**

`test_every_router_with_book_id_also_requires_authentication` の offenders も
`admin_phase2` **のみ**（実測）。`require_api_key` / `require_admin_user_or_key` は
`src/backend/auth.py:99` / `:125` に実在し、bypass でない限り 401/403 を返す本物の依存。

```python
AUTH_MARKERS = (
    "get_current_user",
    "enforce_book_ownership",
    "requires_book_ownership",
    "require_api_key",
    "require_admin_user_or_key",
)
```

> **P1 との整合**: 認証要件を緩めたのではなく正しく認識しただけ。
> 認証依存を持たない router は従来どおり赤のまま（`admin_phase2` 以外は
> 追加前後で offenders が増減しないことを実測で確認済み）。

### 2-2. `tests/security/test_server_route_mount_parity.py`

`ALLOWLIST = {"metrics"}`（:66）→ **理由付き dict に拡張**し、
`_SKIP` の計算を `set()` 経由に修正、理由ゲートを ALLOWLIST にも拡張した。

```python
ALLOWLIST: dict[str, str] = {
    "metrics": (...役割重複...TODO(H1-2): 統合可否を判断する),
    "agent_memory": (...マウント履歴なし / フロント未使用 / Depends 0 件 / 検証は
                       tests/integration/api/test_agent_memory_api.py...TODO(H1-2)),
    "conflicts":    (...同上...TODO(H1-2)),
    "dashboard":    (...同上...TODO(H1-2)),
}

_SKIP = set(ALLOWLIST) | set(CONDITIONAL_MOUNTS)   # dict | set は TypeError になるため必須


def _assert_reasons(entries: dict[str, str], kind: str) -> None:
    for name, reason in entries.items():
        assert reason.strip(), f"{name} の {kind} に理由が無い"
        assert "TODO(H1-" in reason, (
            f"{name} の {kind} に TODO(H1-N) の番号が無い（§9: 数値外れ禁止）"
        )


def test_allowlist_entries_have_a_reason():   # 追加（ゲートの強化）
    _assert_reasons(ALLOWLIST, "ALLOWLIST")

def test_conditional_mounts_have_a_reason():  # 既存を共通ヘルパへ委譲
    _assert_reasons(CONDITIONAL_MOUNTS, "CONDITIONAL_MOUNTS")
```

**やらないこと**: 3 router をマウントしない（`Depends` 認証依存が 0 件で、
マウントすると未認証エンドポイントの公開になる）。削除は Phase 6。

### 2-3. 検証結果（完了）

```
pytest tests/security/  → 88 passed in 6.33s
ruff check（2 ファイル） → All checks passed!
```

---

## 3. Phase 2: config 契約テストとの競合（案A・承認済み）

### 3-1. 経緯（三方の主張）

| 時点 | commit | 内容 |
|---|---|---|
| 外部 | `0576a8f9` | `config/__init__.py` に 4 名前の再バインドを**追加**（+15） |
| 外部 | `1d852094` | その 4 名前が `__all__` に在ることを**契約テストで固定** |
| 当方 | `43b12db2` | 再バインドを**削除**（shim 的挙動の是正）＋呼び出し側を新パスへ移行 |

→ `test_config_keeps_critical_compat_names` と
`test_pipeline_steps_extended` ×4（`patch("config.project_context.ProjectContext")`）
が red。**同一原因**。

### 3-2. 編集内容

**ファイル: `config/__init__.py`（末尾に追記 + `__all__` に 4 名前追加）**

```python
# ------------------------------------------------------------------
# 後方互換の遅延解決（PEP 562）
#
# Phase R3 で shim としての即時再エクスポートを削除したが、旧パス `config.X`
# を参照する外部コード・契約テスト（tests/unit/config/test_public_api.py）との
# 移行猶予として、**アクセスされた時だけ**実体を解決して返す。
#
# 即時 import を戻さない理由:
#   - `import config` のたびに src.domain.styles / project_context を
#     読み込むコストが常に発生する
#   - shim 削除の成果（旧パスが死んでいること）が失われる
#
# `import config.constants` / `import config.project_context` は従来どおり
# ModuleNotFoundError のまま（submodule import は __getattr__ を経由しない）。
# ------------------------------------------------------------------

#: 属性名 -> (実体モジュール, モジュールから取り出す属性名。None ならモジュール自身)
_COMPAT_LAZY_ATTRS: dict[str, tuple[str, str | None]] = {
    "constants": ("src.config.constants", None),
    "project_context": ("src.infrastructure.config.project_context", None),
    "FORBIDDEN_SUMMARY_PATTERNS": ("src.domain.styles", "FORBIDDEN_SUMMARY_PATTERNS"),
    "FORBIDDEN_WORD_REPLACEMENTS": ("src.domain.styles", "FORBIDDEN_WORD_REPLACEMENTS"),
}


def __getattr__(name: str):
    """後方互換の遅延解決。未知の名前は AttributeError（PLOT_STRUCTURES 等の維持）。"""
    target = _COMPAT_LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib
    import warnings

    module_name, attr = target
    module = importlib.import_module(module_name)
    value = module if attr is None else getattr(module, attr)
    warnings.warn(
        f"config.{name} は非推奨です。{module_name} から直接 import してください",
        DeprecationWarning,
        stacklevel=2,
    )
    globals()[name] = value   # 2 回目以降は __getattr__ を呼ばない
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_COMPAT_LAZY_ATTRS))
```

`__all__` の末尾に 4 名前を追加:

```python
    "get_preset_names",
    # 後方互換（遅延解決・上記 __getattr__）。移行完了後に除去する。
    "constants",
    "project_context",
    "FORBIDDEN_SUMMARY_PATTERNS",
    "FORBIDDEN_WORD_REPLACEMENTS",
]
```

### 3-3. 実装時の注意点（検証必須）

| # | 前提 | 検証方法 |
|---|---|---|
| N1 | `hasattr(config, "constants")` が True | `test_config_public_api_names_exist` |
| N2 | `getattr` が None でない | `test_config_public_api_names_are_not_none` |
| N3 | `name in config.__all__` | `test_config_keeps_critical_compat_names` |
| N4 | `importlib.import_module("config.constants")` が **ModuleNotFoundError** | `test_removed_shim_import_fails`（`REMOVED_SHIMS` に `config/constants.py` / `config/project_context.py` が在る） |
| N5 | `importlib.import_module("config.project_context")` が ModuleNotFoundError | 同上 |
| N6 | `assert not hasattr(config, "PLOT_STRUCTURES")` | `test_removed_definitions.py:17` — `__getattr__` が未知名で `AttributeError` を投げること |
| N7 | `patch("config.project_context.ProjectContext")` が解決する | `pkgutil.resolve_name` は `importlib.import_module("config.project_context")` → ImportError → `getattr(config, "project_context")` の順（`/usr/lib/python3.13/pkgutil.py:505-540` で確認済み）。**`__getattr__` が返すモジュールは `src.infrastructure.config.project_context` と同一オブジェクト**なので、パッチは従来と同じ実体に効く |
| N8 | `_strict_import_modules()`（AST の `ImportFrom.module` / `Import.names`）に `config.project_context` が**含まれない** | `__getattr__` 内は文字列でモジュール名を渡す（`importlib.import_module`）ため AST に現れない。`from config.project_context import ...` と書かないこと |
| N9 | `pytest.ini` に `filterwarnings = error` が無い | 確認済み（無い）。`DeprecationWarning` は既定で無視される |

### 3-4. 検証コマンド

```bash
.venv/bin/python -m pytest tests/unit/config/ \
  tests/unit/services/test_pipeline_steps_extended.py \
  tests/regression/test_shim_removal_detection.py \
  tests/unit/story_spine/test_removed_definitions.py \
  -q -p no:cacheprovider
.venv/bin/python -m ruff check config/__init__.py
```

---

## 4. Phase 3: `GET /api/tasks/dag/{dag_id}` の認証限定

### 4-1. 事実（調査済み）

- `src/backend/routers/tasks.py:83 get_dag_status(dag_id: str)` — router レベルの
  `dependencies=[Depends(get_current_user)]`（:25）のみで、**所有権・管理者限定が無い**。
- `DAGGraph`（`src/backend/tasks/dag_models.py:40`）は `dag_id` / `nodes` のみで
  **owner・book_id フィールドが無い**。
- checkpoint は `/tmp/dag_checkpoints`（`dag_persistence.py:37`）。
- `dag_id` は `novel_b{book_id}_ep{ep_num}`（`generation_tasks.py:611`）と
  `orch_{correlation_id}`（`agents/orchestrator.py:119`）の 2 形式 → **全形式から book を導出できない**。
- `dag_status:*` の Redis キーは**誰も書かない**（`tasks.py:103` の読み取りのみ）。
- フロントからの参照なし（`api.generated.ts:2270` の生成型定義のみ）。
- **先例**: 同ファイル `:244` / `:273` に `APIRouter(dependencies=[Depends(require_admin_user_or_key)])`
  が既にある（`require_admin_user_or_key` は import 済み `:9`）。

### 4-2. 編集内容（案A・承認済み）

**ファイル: `src/backend/routers/tasks.py:83`**

```python
@router.get("/dag/{dag_id}")
async def get_dag_status(
    dag_id: str,
    _: User = Depends(require_admin_user_or_key),
):
    """Step 57: Get DAG workflow status, progress, and node execution states.

    所有権の判定が出来ないため管理者/API Key に限定する（P1）:
    - DAGGraph に owner / book_id フィールドが無く、checkpoint から
      所有者を導出できない
    - dag_id は `novel_b{book_id}_ep{ep}` と `orch_{correlation_id}` の
      2 形式があり、正規表現では全形式をカバーできない
    - 返り値に node の error 文字列・実行時間が含まれるため、
      任意ユーザーに開示しない
    TODO(H1-2): DAGGraph に owner_id を持ち、checkpoint に永続化して
      per-owner の照合を行う（設計は §4-3）。
    """
```

> `User` は既に `:10` で import 済み。`Depends` は `:4` で import 済み。

### 4-3. 設計メモ（案B = Phase 3b、本書では実装しない）

1. `DAGGraph` に `owner_id: int | None = None` を追加（Pydantic モデルなので後方互換）。
2. 作成経路（`generation_tasks.py:611` / `agents/orchestrator.py:119`）に user を渡す。
   - `orch_*` は correlation_id 経由で作成されるため、呼び出し元の
     `AgentContext` から user を引き継ぐ必要がある。
3. 読み取り時に `_assert_task_ownership`（同 `:30` に既存実装あり、fail-closed）を流用する。
4. **旧 checkpoint の扱い**: `owner_id is None` の旧ファイルは
   fail-closed（管理者のみ）にする。fail-open にすると移行期間中に全開放される。
5. `dag_status:*` レデッドパス（誰も書かない）はこの際に入力もしないか削除するか判断する。

### 4-4. 検証コマンド

```bash
.venv/bin/python -m pytest tests/unit/test_dag_scheduler_part5_advanced.py \
  tests/unit/test_p4_async_and_db_concurrency.py tests/security/ -q -p no:cacheprovider
```

**テスト影響の事前確認（読み取り済み）**

- `test_p4_async_and_db_concurrency.py:195` は `await get_dag_status("test_dag")` と
  **直接呼び出し**。依存パラメータにデフォルトがあるため引数 1 個で呼べる → 影響なし。
- `test_dag_scheduler_part5_advanced.py:118` は
  `assert response.status_code in (200, 401)`。
  - bypass 有効時: `require_admin_user_or_key` が dev ユーザーを返す → **200** ✓
  - bypass 無効・ヘッダ無し: `oauth2_scheme` が 401 → **401** ✓
  - ヘッダ有りで非 admin: **403** → 既存アサーションに**無い**。
    テストはヘッダを送らないため発生しないが、CI の `AUTH_DISABLED` 設定に注意する。

---

## 5. Phase 4: バージョン 7.0.0 への一括同期

SSOT = `pyproject.toml:3` の `version = "7.0.0"`（`authoritative_version` fixture が読む）。
`src/backend/__init__.py` / `src/cli/main.py` は外部コミット `0576a8f9` で 7.0.0 済み。
`CHANGELOG.md` も `## [7.0.0]` が先頭（`test_changelog_top_entry_matches_pyproject` が緑）。

### 5-1. ファイル別編集

| ファイル | 現状 | 編集 | 検証するテスト |
|---|---|---|---|
| `README.md:9` | `version-6.0.0-brightgreen` / `releases/tag/v6.0.0` | `6.0.0` → `7.0.0`（**同一行の 2 箇所**） | `v5::test_readme_version_matches` / `v6::test_readme_badge_matches_pyproject` / `docs_numbers::test_readme_version_matches_pyproject` |
| `frontend/package.json:4` | `"version": "6.0.0"` | `7.0.0` | `v5::test_frontend_package_json_version` |
| `docker-compose.prod.yml:21,96,149,174` | `autonovel-{backend,backend,frontend,db}:6.0.0` | 4 箇所とも `7.0.0`（正規表現 `^\s*image:\s*autonovel-[\w-]+:(\S+)\s*$` が全て拾う） | `v5::test_prod_compose_image_tags` |
| `docs/openapi.json` `info.version` | `6.0.0` | **再生成**（§5-2） | `docs_router_count::test_openapi_json_version_matches_pyproject` |
| `docs/STATUS.md:17-21` | 表の 5 行が `6.0.0` | `**7.0.0**` と `7.0.0` ×3、`[7.0.0] - ...`（CHANGELOG 先頭の日付に合わせる） | `status_doc::test_version_section_matches_pyproject`（`## 1. バージョン` 節に `**7.0.0**` が在ること） |

> `test_version_section_matches_pyproject` は `text.split("## 1. バージョン", 1)[-1].split("\n---", 1)[0]`
> の範囲を検査する。`docs/STATUS.md:13-25` の節が対象。`**5.3.0**` が無いことも要求される。

### 5-2. 生成物の再生成（P3）

```bash
.venv/bin/python scripts/generate_openapi.py      # docs/openapi.json を再生成
.venv/bin/python scripts/generate_ts_types.py     # frontend/src/types/api.generated.ts を再生成
git diff --stat docs/openapi.json frontend/src/types/api.generated.ts
```

- `openapi.json` の差分は `info.version` 以外が動かないこと（動いた場合は
  並行コミットによるルータ変更の混入なので、差分を確認してからコミットする）。
- `api.generated.ts` の差分も同様に確認する（このファイルに同期テストは無いが、
  P3 により必ず再生成・diff 確認する）。

### 5-3. テスト自体の陳腐化を是正（`test_pyproject_version_is_v6`）

**ファイル: `tests/regression/test_v6_version_consistency.py:22-23`**

```python
# 旧: assert _pyproject_version() == "6.0.0"
def test_pyproject_version_is_current_release():
    """pyproject の版数が現行リリースであること（ハードコードをやめ SSOT 一致に）。"""
    version = _pyproject_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"SemVer 形式でない: {version}"
    # CHANGELOG 先頭エントリ == pyproject（下の test_changelog_top_entry_matches_pyproject と
    # 同じ判定を、版数の「今どれくらい新しいか」を固定しない形で担保する）
    assert _changelog_top_version() == version
```

> 関数名を変えてもよいが、**テスト名を変えた場合は**同ファイル内の他テストと
> `tests/regression/test_docs_numbers_consistency.py::test_no_legacy_5_3_0_claims`
> （`README.md` / `docs/STATUS.md` に旧版数の主張が無いこと）の整合を確認する。
> 最小変更にするなら **関数名はそのまま残し、アサーションだけ SSOT 一致に替える**。

### 5-4. 検証コマンド

```bash
.venv/bin/python -m pytest tests/regression/test_v5_version_consistency.py \
  tests/regression/test_v6_version_consistency.py \
  tests/regression/test_docs_numbers_consistency.py \
  tests/regression/test_docs_router_count_matches_reality.py \
  tests/regression/test_status_doc_has_effect_measurement.py \
  tests/unit/cli/test_cli_main.py -q -p no:cacheprovider
```

---

## 6. Phase 5: lint / ruff 負債

### 6-1. 現状と目標（実測）

`ruff check src tests --statistics` = **148 件** / `LINT_ERROR_BUDGET = 122` → **−26 必要**。

| ルール | 件数 | 自動修正 | 対処方針 |
|---|---|---|---|
| F401 unused-import | 70 | `--fix` 可 | **手動判断**（P1: 機械削除禁止） |
| E741 ambiguous-name | 21 | 不可 | 変数リネーム（`l` → `lines` 等） |
| E712 true/false-comparison | 17 | 不可 | `assert x == True` → `assert x` |
| F841 unused-variable | 16 | 不可 | 未使用代入の削除（副作用確認要） |
| F811 redefined | 10 | 一部 | 二重定義の削除 |
| E701 multiple-stmt | 6 | 不可 | 行分割 |
| F601 dup-dict-key | 4 | 不可 | 重複キーの除去（**辞書の意味が変わる**） |
| F821 undefined-name | 2 | 不可 | **実 bug 修正（必須）** |
| E711 none-comparison | 1 | 不可 | `== None` → `is None` |
| F403 import-star | 1 | 不可 | 明示 import へ |

### 6-2. 実行手順（−28 を狙う。予算 122 に対し 120 で余裕 2）

**Step A: F821 ×2（必須 — 2 つのゲートを同時に解消）**

| 箇所 | 症状 | 修正 |
|---|---|---|
| `src/audit/pairwise_selection.py:54` | `is_pairwise_enabled()` が未定義。`src/audit/calibration_store.py:199` に定義あり | import 節（`:9` の直後）に `from src.audit.calibration_store import is_pairwise_enabled` を追加。<br>**循環 import なしを確認済み**: `calibration_store` の import は stdlib + `yaml` のみ |
| `src/llm/adapters/prompts.py:139` | `quality: Optional[str] = None` の `Optional` 未定義（`from __future__ import annotations` でも ruff は F821 を出す） | ファイル先頭（`:3` の直後）に `from typing import Optional` を追加。使用は 1 箇所のみ |

→ −2（`test_ruff_reports_no_f821` と `test_ruff_clean_llm` の**両方**が解消。
`test_ruff_clean_llm` の対象 `src/llm src/core/llm src/services/llm` の違反は
実測で **F821 1 件のみ**）。

**Step B: `tests/generation/test_pdca_controller.py` の E712 ×17（最大の収益）**

E712 17 件は**全てこの 1 ファイル**に集中（実測）。両メソッドの戻り型は
`bool` であることを `src/generation/pdca_controller.py:29,38` で確認済みなので、

```python
# 前
assert controller.should_regenerate_full_text() == False
assert controller.can_do_local_patch() == True
# 後（意味完全等価）
assert not controller.should_regenerate_full_text()
assert controller.can_do_local_patch()
```

→ −17（累計 −19）

**Step C: E741 のうち安全な 9 件（`l` のリネーム）**

| ファイル | 件数 |
|---|---|
| `tests/unit/story_spine/test_resolver_combinatorial.py`（:11,23,31,40,52） | 5 |
| `tests/unit/story_spine/test_resolver_no_llm.py`（:51） | 1 |
| `tests/unit/test_blind_review_purifier.py`（:19,20,21） | 3 |

→ −9（累計 **−28 → 120 件**、予算 122 に対し余裕 2）

> **追加の余裕が欲しい場合**（推奨）: F401 のうち「再エクスポートでない」ことを
> 手動で確認できたものだけを削る。候補（全て `tests/` 配下で明確に未使用）:
> `tests/audit/test_calibration_store.py` の `os` / `pathlib.Path` / `pytest`（3）、
> `tests/regression/test_alembic_env_isolation.py` の `pathlib.Path` / `pytest` /
> `alembic.command`（3）、`tests/regression/test_docker_copy_paths.py` の `re`（1）。
> → 追加 −7 で **113 件**。
> **`src/` 配下の F401 は原則触らない**（`src/audit/perturbation/suite.py:20` の
> `check_retest_stability` は再エクスポートの可能性がある）。

**Step D: env hygiene 1 件（`test_no_new_env_direct_assignment_without_monkeypatch`）**

違反は実測で **1 件のみ**:

```
tests/contract/test_v6_audit_parallel_equivalence.py:36
    os.environ["ENABLE_AUDIT_LEGACY_CORE"] = "true"
```

→ `monkeypatch.setenv("ENABLE_AUDIT_LEGACY_CORE", "true")` に書き換える。
**注意**: 対象が関数内の局所代入なら `monkeypatch` fixture を引数に足すだけ。
モジュールレベル（import 時）で実行されている場合は
`try/finally` で復元する形にし、`ALLOWED_FILES` に**理由コメント付き**で追加する。
どちらになるかは `:36` のインデントを見て判断する。

### 6-3. 禁止事項と守るべきセンティネル

- **`ruff check --fix` の一括適用を `src/` にかけない**。
  `tests/regression/test_lint_budget.py:29` の `REEXPORT_SENTINEL = "src/narrative_balancer"`
  は、F401 機械削除で `ImportError` になった実績から置かれている。
- 触ったら必ず次を回す:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_lint_budget.py -q -p no:cacheprovider
  ```
  内訳 `test_reexport_modules_still_importable` / `test_reexport_names_still_exposed` /
  `test_non_whitespace_rules_are_known(F401,F841,F811)` を含む。
  > `test_non_whitespace_rules_are_known` は「キーが在れば >0」を要求する。
  > ruff の `--statistics` は 0 件のルールを出力しないので、**0 件にしても問題ない**。
- **`config/ci_lint_baseline.json`（`ruff_errors: 85`）は触らない**。
  消費者 `tests/regression/test_lint_baseline_integrity.py::test_ruff_check_baseline` は
  `baseline >= 0` のみを assert しており、実測値と比較しない。
  （`scripts/ci_lint_ratchet.py` は手動スクリプト。削減後の更新は任意の追加作業。）

### 6-4. 検証コマンド

```bash
.venv/bin/python -m ruff check src tests --statistics          # 合計 <= 122
.venv/bin/python -m pytest tests/regression/test_lint_budget.py \
  tests/regression/test_no_undefined_names.py \
  tests/regression/test_llm_unification_complete.py \
  tests/regression/test_env_var_hygiene.py \
  tests/regression/test_lint_baseline_integrity.py -q -p no:cacheprovider
```

---

## 7. Phase 6: 残存 19 件（**本書の範囲外**・調査して別計画）

| グループ | 件数 | 調査の着眼点 |
|---|---|---|
| e2e | 5 | `test_production_e2e` は FileNotFound。テストデータ/フィクスチャの欠落か |
| perf（`tests/perf/`） | 6 | 閾値依存。pgvector 2 件は FK 制約違反で **FAILED→ERROR に移行**（base 由来） |
| performance | 2 + **1 新規** | `dsp_perf` / `fusion_perf` は base 由来。**`test_compression_benchmark` は新規**（§8） |
| regression（docs 系） | 1 | `test_readme_llm_calls_matches_measured_value` — README の「10 回」が STATUS.md と不一致 |
| regression（基盤） | 3 | `test_conftest_mock_llm_adapter_fixture` / `test_subprocess_encoding_gate` / `test_t6_plan_completion` |
| generation | 1 | `test_pdca_pipeline_integration` |
| database | 1 | `test_book_repository_concurrency` |
| unit（flaky） | 1 | `test_get_db_manager_singleton` — `var/reports/qa_baseline_failures.txt` に既知 flaky として記載 |

### 7.1 新規失敗 `test_compression_benchmark` の調査結果（追記）

- **隔離実行でも再現**（`1 failed, 5 passed in 7.03s`）。
  `10KB: current=926.02ms > threshold 553.66ms`（baseline 369.11ms × 1.5）。
- `test_benchmark_baseline_save`（同ファイル :127）が**毎回 baseline を上書き**する。
  base worktree と HEAD でファイル差分は **0**（`git diff 79b0d041 HEAD` 空）。
- baseline 自体の分散が大きい（`stdev 127.6ms` / `max 587.77ms`）うえ、
  回帰判定は **1 回のみの単発測定**で 1.5× 閾値。
- → **本物の機能回帰ではなく、測定方式（単発・高分散・負荷依存）の問題**と推定。
  Phase 6 で「3 回測定の中央値 + 事前ウォームアップ」への書き換えを提案する。
  機械の都合で 3 回測定する間は他のテストと並列実行しない（P5 の collection speed と同様）。

---

## 8. 検証マトリクス（フェーズごとの完了条件）

| Phase | コマンド | 期待 |
|---|---|---|
| 1 | `pytest tests/security/ -q -p no:cacheprovider` | 88 passed（**済**） |
| 1 | `ruff check tests/security/*.py` | clean（**済**） |
| 2 | `pytest tests/unit/config/ tests/unit/services/test_pipeline_steps_extended.py tests/regression/test_shim_removal_detection.py tests/unit/story_spine/test_removed_definitions.py -q` | 全 pass |
| 3 | `pytest tests/unit/test_dag_scheduler_part5_advanced.py tests/unit/test_p4_async_and_db_concurrency.py tests/security/ -q` | 全 pass |
| 4 | `pytest tests/regression/test_v5_version_consistency.py tests/regression/test_v6_version_consistency.py tests/regression/test_docs_numbers_consistency.py tests/regression/test_docs_router_count_matches_reality.py tests/regression/test_status_doc_has_effect_measurement.py tests/unit/cli/test_cli_main.py -q` | 全 pass |
| 4 | `git diff --stat docs/openapi.json frontend/src/types/api.generated.ts` | 差分を確認済み |
| 5 | `ruff check src tests --statistics` | `Found N errors` で N ≤ 122 |
| 5 | `pytest tests/regression/test_lint_budget.py tests/regression/test_no_undefined_names.py tests/regression/test_llm_unification_complete.py tests/regression/test_env_var_hygiene.py -q` | 全 pass |
| 最終 | `pytest tests/ -q -p no:cacheprovider --continue-on-collection-errors` | 失敗 = Phase 6 の base 由来 18 件 + 環境依存 1 件のみ |

---

## 9. リスクとロールバック

| リスク | 対策 | ロールバック |
|---|---|---|
| 並行セッションが同一ファイルを編集（`tasks.py` / `config/__init__.py` で発生済み） | 各コミット直前に §10 の P4 チェック | 衝突時は**当方の変更を破棄して外部に合わせる**（外部が契約テストを持つ場合） |
| Phase 2 の `__getattr__` が `import config.constants` を通してしまう | N4/N5 の `pytest.raises(ModuleNotFoundError)` で確認 | `__getattr__` の対象を 4 名前から絞る |
| Phase 3 が `test_get_dag_status_endpoint` の `in (200, 401)` を壊す | 403 が出る条件（ヘッダ付き非 admin）をテストが使わないことを確認済み | 依存を router レベルの `dependencies` に移す |
| Phase 4 の再生成が並行コミットのルータ変更を混入させる | `git diff` を見て `info.version` 以外が動いていれば中断 | 再生成ファイルのみ `git checkout --` |
| Phase 5 の F401 機械削除が再エクスポートを壊す | `src/` は手動判断のみ、`test_lint_budget.py` を都度実行 | 該当コミットを revert |
| full run の collection speed / perf ゲートが負荷で揺れる | 測定は 3 回・並列実行しない | 記録して Phase 6 へ送る |

---

## 10. P4 チェックリスト（各コミット直前に必ず実行）

```bash
git status --short                     # 意図した変更のみ（golden / baseline / var の副作用を revert）
git log -3 --format="%h %s"            # 並行コミットが入っていないこと
.venv/bin/python -m pytest tests/unit/config/test_public_api.py -q -p no:cacheprovider   # 緑
```

**副作用リセット（full run の後に必須）**

```bash
git checkout -- tests/benchmarks/compression_baseline.json   # 他に dirty が出たら同様
```

テストは追跡ファイル（golden JSON / `compression_baseline` / `var/import_graph.json` /
`index.yaml` 等）を書き換えるため、**full run の直後は必ず `git status` を見る**。
