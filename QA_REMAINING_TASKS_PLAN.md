# 残存タスク 実装計画書

作成日: 2026-10-03
基準コミット: `780c896`（公開前監査の修正群）
対象: Tier1 ベースラインに記載された残存失敗 + 調査で判明した未記載の問題
状態: **未着手（計画のみ）**

---

## 0. 前提の訂正（作業着手前に必ず読むこと）

直近の調査で、当初，把握していた前提に誤りが複数見つかった。計画の前提を以下に訂正する。

| 当初の前提 | 実測 | 確認方法 |
|---|---|---|
| `test_database_core.py` 20件は(raw string 拒否で)すべて同じ原因 | **違う**。6種別の独立原因。raw string 由来は3件のみ | `pytest tests/backend/test_database_core.py --tb=line` |
| `test_v53_long_form_integrity.py` が6件失敗 | **単独では0件**。順序依存で2件のみ | 単独実行 / `tests/unit` 後に実行 |
| `test_v53_concurrent_transition.py` がベースラインにある | **ない**。Tier1 順序では通過するため baseline に載らず、**単独で7件失敗** | `reports/qa_tier_baseline.json` / 単独実行 |
| `test_chroma_store.py` が失敗している | **既に緑**（89 passed）。ベースラインにも記載なし | 単独実行 |
| `test_collection_health_gate.py` / `test_lint_budget.py` が失敗中 | **現在绿**。baseline に残る stale エントリ | 単独実行 = 9 passed |

**この訂正は計画自体の射程を変える。** 特に「ratchet（品質ゲート）が注文依存を検出できない」
という穴が判明しており、これは前回自分が設計した機構の欠陥である（→ タスク T12）。

---

## 1. タスク一覧（優先度順）

### 優先度尺度
- **P0**: 公開阻害。製品が壊れている、または 检测機構が機能していない
- **P1**: 公開前リリース推奨。テスト/契約の陳腐化
- **P2**: 品質・運用

---

### T1【P0】`tenants` テーブルが Base.metadata に未登録

**影響範囲**: DB スキーマ構築の全域

**症状**
`test_v53_concurrent_transition.py` が単独実行で 7 件失敗:
```
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column
'books.tenant_id' could not find table 'tenants'
```

**根本原因**（`src/backend/database/models.py`）
- `models.py:77,95` が `tenant_id = Column(Integer, ForeignKey("tenants.id"))` を宣言
- `Tenant` は `models_tenant.py:13` にあるが、`models.py` の「全テーブルを同一 Base に登録する」
  意図の副作用 import 一覧に `models_tenant` が**漏れている**
- 結果 `tenants` が `Base.metadata` に未登録
- 副作用: `init_db` の開発フォールバック `InfraBase.metadata.create_all(engine)`（`core.py:427`）も
  `NoReferencedTableError` で失敗する。本番は Alembic が主経路なので顕在化しないが、
  **create_all 経路は恒久的に壊れている**

**作業手順**
1. `src/backend/database/models.py` の副作用 import 群に以下を追加
   ```python
   from src.backend.database.models_tenant import Tenant, TenantMember  # noqa: F401
   ```
2. `tests/regression/test_v53_concurrent_transition.py` にも同じ import を追加（テスト単独実行の自律性）
3. `Base.metadata` に `tenants` が含まれることを検証

**工数**: 3〜5 行（src） + 1 行（test）

**回帰テスト（新規作成）**
```python
# tests/backend/test_metadata_completeness.py
def test_all_foreign_key_targets_are_registered():
    """Base.metadata に登録された全テーブルの FK 参照先が実在すること。"""
    # create_all が NoReferencedTableError を出さないことの直接検証
def test_tenant_table_is_registered():
    assert "tenants" in Base.metadata.tables
```
**これが核心のテスト**。「うっかり漏らした」を検出する一般化されたゲート。

**受け入れ基準**: `pytest tests/regression/test_v53_concurrent_transition.py` が単独で 7 passed。
`test_metadata_completeness.py` が緑。

**リスク**: 低。副作用 import の追加のみ。

---

### T2【P0】Alembic が既存のロガー 500 個を無効化している

**影響範囲**: テストの順序依存（CI 非決定性）／アプリログの消失

**症状**
`test_v53_long_form_integrity.py` の 2 件が、`tests/unit` を実行した後にだけ失敗する。
`caplog` でログを捕捉できない。

**根本原因**（連鎖を実測で確認済み）
1. `tests/unit/core/test_core_without_plugins.py:59` と
   `tests/unit/api/test_plugin_conditional_routing.py:24` が
   `sys.modules.pop("src.backend.server")` → 再 import
   → `tests/conftest.py:39-47` の `init_db` スタブが**静かに失われる**
2. `tests/unit/test_graphrag.py:422` の `client` フィクスチャが `with TestClient(app)` で
   lifespan を発火
3. lifespan（`server.py:77-81`）→ `configure_logging()` → 本物の `init_db()`
   → `_run_alembic_upgrade()` → `src/backend/alembic/env.py:27` が
   `logging.config.fileConfig(config.config_file_name)` を呼ぶ
4. `fileConfig` の `disable_existing_loggers` 既定は **True** → それまでに生成済みの
   全ロガー（実測 500 個）に `disabled=True` が焼き付く
5. `caplog.at_level()` は level だけを下げ `disabled` は解除しない → `logger.info` が無言で死に

**最小再現（確証）**
```
pytest tests/unit/core/test_core_without_plugins.py \
       tests/unit/test_graphrag.py::test_graph_router \
       tests/regression/test_v53_long_form_integrity.py
→ 2 failed, disabled_loggers: 0 → 286
```

**作業手順**
1. **恒久策（製品側・必須）**: `src/backend/alembic/env.py:27` を
   `logging.config.fileConfig(config.config_file_name, disable_existing_loggers=False)` に。
   プロセス内ロガーを巻き込むのはアプリ本体でも障害
2. **恒久策（テスト側・推奨）**: `tests/conftest.py` の `pytest_configure` の
   `except Exception: pass`（39-47行）をやめ、`sys.modules.pop` 後の
   `init_db` 差し替えが静かに失われる構造を排除する
3. **テスト堅牢化**: `tests/regression/conftest.py`（新設または既存に追加）に
   `logger.disabled` を退避・復元する autouse フィクスチャ。
   同条件のloge依存テストが今後すべて落ちるため、防衛壁になる

**工数**: 1 行（env.py） + 10〜15 行（conftest） + 10 行（フィクスチャ）

**回帰テスト（新規作成）**
```python
# tests/regression/test_logging_isolation_gate.py
def test_fileconfig_does_not_disable_existing_loggers():
    """alembic env が既存ロガーを無効化しないこと。"""
    # env.py の fileConfig 呼び出しに disable_existing_loggers=False が
    # 渡されていることを AST で検証（実装修正の再発防止）

def test_autouse_logger_disabled_guard_restores_state():
    """フィクスチャが logger.disabled を復元すること。"""
```

**受け入れ基準**: 上記最小再現コマンドで 0 failed。`tests/regression` 全体が緑（v53 long_form 含む）。

**リスク**: 低。`disable_existing_loggers=False` は意図どおりの挙動。
ただしアプリログの出力量が増える可能性があり、CI ログierrを注視。

---

### T3【P0】`executor_manager` シングルトンが lifespan で死に、後続テストを無言で壊す

**影響範囲**: `semantic_cache`、および executor 利用テスト全般

**症状**
`tests/unit/test_semantic_cache.py::test_evict_if_needed` が単独では pass、
`tests/unit/test_marketing_agent.py` の後に fail。

**根本原因**（実証済み）
1. `server.py:125-127` の lifespan shutdown が `executor_manager.shutdown()` を呼ぶ
2. `ExecutorManager` はシングルトン。shutdown 後 `io_executor`/`cpu_executor` が恒久的に死に、
   以降プロセス全体で `RuntimeError: cannot schedule new futures after shutdown`
3. `tests/unit/test_marketing_agent.py:142` の `with TestClient(app)` が lifespan を発火
4. `src/services/semantic_cache.py` の `evict_if_needed` が **bare `except Exception`** で
   その RuntimeError を**完全に握り潰す** → `delete_by_id` が 0 回 → `assert_called_once()` 失敗

**作業手順**
1. `semantic_cache.evict_if_needed` の bare `except` を撤去し `logger.exception` で可視化
2. `tests/unit/conftest.py` に executor の autouse 隔離フィクスチャを追加
3. `ExecutorManager.shutdown()` を冪等・再生成可能にする

**工数**: 5〜10 行（1） + 10〜15 行（2） + 10〜15 行（3）

**回帰テスト（新規作成）**
```python
def test_evict_if_needed_surfaces_executor_failure():
    """run_io が例外を投げたとき握り潰されないこと（現状は黙って 0 回）。"""
def test_run_io_works_after_shutdown():
    """shutdown 後の契約。冪等か再生成可能かを明文化。"""
```

**受け入れ基準**: `pytest tests/unit/test_marketing_agent.py tests/unit/test_semantic_cache.py` が緑。

**リスク**: 中。`semantic_cache` の例外処理を変えるため、障害時に表面化するエラーが増える。
**これは意図的**（無言で失敗する方が悪い）。

---

### T4【P0・要判断】`DatabaseConnectionWrapper` がシムに gut されている

**影響範囲**: `tests/backend/test_database_core.py` の 11 件

**症状**
```
TypeError: DatabaseConnectionWrapper() takes no arguments   （11件）
```

**根本原因**
- `src/backend/database/core.py:38-40` の `DatabaseConnectionWrapper` が `pass` だけのシム
- 大規模 savepoint（`72ad1bf`）で実体が削除されたが、テストは残存
- さらに `core.py:212-243` の `get_conn()` は**別の private `_CompatWrapper`** を返す
  → 同 functionalities が二重定義

**2つの選択肢（判断が必要）**

| | (a) 実体復元・統合 | (b) 削除 |
|---|---|---|
| 工数 | 60〜90 行 | 15 行 |
| テスト | 11件が緑 | 11件を削除 |
| 製品価値 | `get_conn()` が deprecated のため実質ゼロ | 同左（誤用を future で防ぐ） |
| リスク | 低いがシム再做構築が必要 | 低 |

**推奨: (b) 削除**。`get_conn()` は deprecated であり、dead code の残置は
誤用の温床になる。復元する価値が無い。

**作業手順（(b) の場合）**
1. `src/backend/database/core.py` から `DatabaseConnectionWrapper` と `_CompatWrapper` を削除
2. `get_conn()` が `DatabaseManager.get_session()` 等を返す実装に整理（または削除）
3. `tests/backend/test_database_core.py` の該当 11 テストを削除

**回帰テスト**: 削除が正しい場合、**追加すべき回帰テストは無い**（存在しない功能的を
テストに置いてはいけない）。ただし `get_conn()` を削除するなら、
呼び出し元が 0 であることを静的確認するテストを追加。

**受け入れ基準**: `test_database_core.py` の 11 件が解消。

**リスク**: 中。公開 API の削除を含む。外部利用の有無を事前に確認すること。

---

### T5【P1】`test_database_core.py` 残り 8 件を現状の契約に追従

**影響範囲**: 同ファイル

**症状と原因（6種別を実測確認済み）**

| 症状 | 件数 | 分類 | 修正 |
|---|---|---|---|
| `DatabaseConnectionWrapper() takes no arguments` | 11 | 製品 | → T4 |
| `\tmp\test.db == /tmp/test.db` | 1 | 環境（Windows） | `str(Path("/tmp") / "x.db")` で比較 |
| `_warned_about_str_sql` が無い | 1 | テスト（陳腐化） | private 属性への依存を削除 |
| `no longer accepts raw strings` | 3 | テスト（意図的変更に未追従） | `text()` を使うよう書き換え |
| `Mock does not support async context manager` | 1 | テスト（モック不正） | `__aenter__` を追加 |
| `does not have the attribute 'select'` | 1 | テスト（patch target 不在） | 関数内 import の patch 方法を修正 |
| `NameError: name 'mock' is not defined` | 1 | テスト自身のバグ | `Mock.ANY` に修正 |

**作業手順**
1. 上表の「修正」列に従って各テストを直す
2. raw string 拒否 3 件は、`text()` を使う正常系テストに書き換える

**工数**: 38〜58 行

**回帰テスト（既存テストの刷新が主)** — 新規 Additionally:
```python
def test_execute_rejects_raw_string():
    """raw string 拒否という意図を固定（現状この意図のテストが0件）。"""
def test_execute_accepts_text_clause():
    """text() が通る正常系の正面確認。"""
def test_save_internal_state_select_patch_scope():
    """関数内 import を patch する正しい方法を固定。"""
def test_create_snapshot_path_is_platform_neutral():
    """Windows/POSIX 両方で通るパス比較。"""
```

**受け入れ基準**: `test_database_core.py` 全体が緑。

**リスク**: 低。テストのみの変更（+T4 の src 変更）。

---

### T6【P1】`ForeshadowingResolutionStep` の未実装テストを整理

**影響範囲**: `tests/services/test_foreshadowing_resolution_step.py`（453行）

**症状**: 6 件失敗。エラー文言が登録ステップと不一致。

**根本原因（重要）**
- `git log --all -S "class ForeshadowingResolutionStep"` → **空。全履歴で一度も実装されたことがない**
- テストの line 2 は `ForeshadowingRegistrationStep as ForeshadowingResolutionStep` と alias しており、
  import は通るが**別物**（登録ステップ）を叩いている
- alias があるため「この Step の失敗」ではなく「登録ステップの失敗」に見えてしまう

**、なぜ「実装」ではなく「テスト削除」が正しいか**
1. テストの仕様は製品として成立しない。テストは
   「`hang_volume == current_volume` かつ `hang_episode == current_episode` の伏線を解決済みにする」
   と主張しており、**張った章と回収した章が同一**の伏線が許される意味論になっていない
2. 解決判定は既に `ForeshadowingService.check_and_resolve()`（`foreshadowing_service.py:42`）が
   本番経路（`episode_writer.py:374`、`writing_langgraph.py:779`）で担っている。
   新 Step を入れると同一伏線に 2 系統の回収判定が競合し、片方が誤った「機械的回収」を食う
3. なお `ForeshadowingRegistrationStep` すらパイプラインに配線されていない（`src/` 内で呼び出し元ゼロ）

**作業手順**
1. `tests/services/test_foreshadowing_resolution_step.py` を削除
2. `reports/qa_tier_baseline.json` から該当 1 行を除去
3. 削除理由を `docs/TEST_STRATEGY.md` に記録（再発防止）
4. **カバレッジを正しい場所で取り直す**（下記回帰テスト）

**工数**: 1 行 + 1 行 + 5〜8 行

**回帰テスト（新規作成・削除したカバレッジの代替）**
```python
# tests/services/test_foreshadowing_service_resolution.py
def test_check_and_resolve_marks_detected_foreshadowing():
    """本文解析で回収判定された伏線が repository.resolve() 経由で更新される。
    本番経路（episode_writer.py:374）と同じ入口の正面テスト。"""
def test_check_and_resolve_isolates_single_item_failure():
    """per-item 例外隔離（foreshadowing_service.py:94-98）を固定。"""
def test_check_and_resolve_distinguishes_contracted_from_uncontracted():
    """target_ep is None を「契約済み」扱いしない挙動を固定。"""
```

**受け入れ基準**: baseline から除去され、ratchet が緑。上記新規 3 件が緑。

**リスク**: 中。テストを削除するため、「減らしたカバレッジ」=new test で必ず補充すること。

---

### T7【P1】`test_trim_all_pinned_cannot_reduce` のトークナイザ依存を除去

**影響範囲**: 1 件

**根本原因**
`layer1_keywords.py:29-40` の `count_tokens()` は tiktoken があれば BPE、なければ
`len(text) * 1.5` にフォールバックする。tiktoken は**必須依存**なので CI では常に BPE 経路。
実測: `"F"*200` は tiktoken で **25**（BPE が圧縮）→ 整形込み 42。
テストは fallback 値（300）を前提に `assert out.token_count > 300` 前提にしている。

製品コード（`layer4_trimming.py:355-371`）は正しい。

**作業手順**
1. `assert out.token_count > 300` を `count_tokens()` 基準の相対比較に置き換える
2. より強い不変条件 `"F"*200 in out.compressed_text`（事実が1バイトも削られていない）を追加

**工数**: 5〜7 行

**回帰テスト（新規作成）**
```python
def test_trim_all_pinned_keeps_pinned_fact_intact():
    """トークナイザ完全非依存。不変条件で固定する。"""
def test_count_tokens_fallback_is_length_times_one_point_five():
    """monkeypatch で tiktoken import を失敗させ fallback 分岐を固定。
    現状この分岐のテストが 0 件。"""
def test_count_tokens_is_monotonic_in_both_backends():
    """両バックエンドで単調増加。"""
```

**受け入れ基準**: 1 件が緑。tiktoken 有無の両方で通ること。

**リスク**: 低。

---

### T8【P1】`DatabaseManagerProtocol` の型契約矛盾を解消

**影響範囲**: `src/core/interfaces.py`

**症状**: `interfaces.py:154-159` の `DatabaseManagerProtocol` は `query: str` と宣言。
実装（`core.py:276-280`）は str を **拒否** する。契約が矛盾。

**根本原因**: raw string 拒否の導入が**途中で止まった**。
`- `fetch_one`/`fetch_all`/`execute`/`fetch_lastrowid`/`enqueue_write` は `src/` 内に呼び出し元ゼロ
  → 拒否のセキュリティ効果はゼロ（grep で確認）
-  **`fetch_lastrowid`（`core.py:312-315`）は拒否されていない**。
  `exec_driver_sql(sql: str, params)` で生の str を通す → 同一クラス内で一貫性がなく、
  実質的な注入面が開いたまま

**作業手順**
1. `interfaces.py` の Protocol を実装に合わせ `TextClause` 型に変更
2. `fetch_lastrowid` にも raw str 拒否を追加（一貫性）

**工数**: 6〜8 行 + 4〜6 行

**回帰テスト（新規作成）**
```python
def test_protocol_signature_matches_implementation():
    """inspect.signature(Protocol) と実装の型注釈を突き合わせる。
    「宣言は str / 実装は拒否」の状態ognegre を検出できる。"""
def test_fetch_lastrowid_rejects_raw_string():
    """拒否漏れを塞いだ後、その意図を固定。"""
```

**受け入れ基準**: 型契約の矛盾がなくなる。既存テストは緑のまま。

**リスク**: 低。`fetch_lastrowid` に拒否を追加すると hypothetical な呼び出しが壊れるが、
`src/` 内に呼び出し元ゼロのため実害なし。

---

### T9【P1】`test_v53_long_form_integrity` のログ依存を堅牢化（テスト側）

T2 の作業手順 3（autouse フィクスチャ）のみ。本体 details は T2 を参照。

**受け入れ基準**: `tests/regression` 全体が単独実行でも緑。

---

### T10【P2】ratchet ベースラインの stale エントリを除去

**症状**: `test_collection_health_gate.py` / `test_lint_budget.py` は現在緑だが baseline に残る。

**作業手順**: `python scripts/ci_tier_ratchet.py --update`

**工数**: 実行のみ

---

### T11【P2・要判断】`BookRepository` の重複定義を解消

**症状**: `src/infrastructure/repositories/book.py` と
`src/backend/database/repository.py:543` に同名クラス。
誤った方を参照すると B2 のような AttributeError、
もう一方は循環 import で `ImportError`。

**選択肢**: (a) 一本化（改名して混乱を除去）、(b) 削除。

**工数**: 30〜60 行

**要判断**: 公開後の次イテレーション。

---

### T12【P2】ratchet の「順序依存テスト検出できない」穴を塞ぐ

**これは前回自分が設計した機構の欠陥であり、最優先で記録する。**

**症状**
`tests/regression/test_v53_concurrent_transition.py` は:
- 単独実行 → **7 件失敗**
- Tier1 の順序（`tests/unit` → `tests/backend` → ... → `tests/regression`） → **通過**

したがって `reports/qa_tier_baseline.json` に載らず、
`ci_tier_ratchet.py` はこのファイルの回帰を**検出できない**。

**根本原因**
`tests/unit/test_auth_real_session.py:7` など複数の unit テストが
`src.backend.database.models_tenant` を import する副作用で、
`tests/regression` 実行時点では `tenants` が `Base.metadata` に登録済みの状態になる。
ratchet は固定順序で 1 回だけ実行するため、
「他テストの副作用に依存しているテスト」を検出する手段が無い。

**作業手順（選択肢 2 つ）**
1. **strict（推奨）**: ゲートを追加し、`tests/regression` の各ファイルを
   **単独実行**して 1 件でも落ちたら検出する。
   CI 時間は増えるが（regression 全ファイルの単独実行 ≈ 数分）、
   検出力が劇的に上がる
2. **軽量**: conftest で `sys.modules` の导入状態を隔離する autouse フィクスチャを
   追加し、副作用の連鎖自体を断つ

**工数**: (1) 約 20〜30 行 / (2) 約 10〜15 行

**回帰テスト（新規作成）**
```python
# tests/regression/test_test_isolation_gate.py
def test_regression_files_pass_in_isolation():
    """tests/regression 配下の各ファイルが単独で緑であること。
    順序依存は「単体では動く」が「他テスト込みで壊れる」形でしか現れないため、
    ファイル単独実行で検出する。"""
def test_gate_detects_order_dependency():
    """検出能力の自己テスト。意図的に失敗するファイルを一時生成し、
    ゲートが検出できることを確認する。"""
```

**受け入れ基準**: `test_v53_concurrent_transition.py` が単独で緑（이는 T1 の成果）。
ゲートが「単独で落ちるファイル」を検出できる。

**リスク**: 中。CI 実行時間が数分増える。Ratchet の設計を 2 段にするため、
運用側の理解が必要。

---

## 2. マイルストーン

| MS | 内容 | タスク | 完了条件 |
|---|---|---|---|
| **MS1** | 製品バグの解消（Detection機構が機能する状態に） | T1, T2, T3 | ratchet が緑。v53/concurrent 単独で緑。ログ順序依存が解消 |
| **MS2** | 陳腐化テストの是正 | T5, T6, T7 | `tests/backend` と `tests/services` が緑 |
| **MS3** | 型契約と衛生 | T8, T10, T4 | `test_database_core.py` 全体が緑。baseline が実測と一致 |
| **MS4** | 回帰機構の穴を塞ぐ | T12 | 順序依存テストを検出できる |
| **MS5** | 構造的負債（次イテレーション） | T11 | 要判断 |

---

## 3. テスト計画

### 3.1 全体方針

今回見つかった全バグの共通点は「**意図的な強化に対応するテストが追従せず、
静かに検証力を失っていた**」こと。したがってテストの追加方針は
「数を増やす」ではなく「**検証力 lower bound を固定する**」に置く。

| 層 | 目的 | 対象 |
|---|---|---|
| 単体（契約テスト） | 意図した契約を明文化する | T5, T7, T8 の新規テスト |
| 結合（独立実行テスト） | 1ファイル単独で緑であることを保証 | T1 の metadata 完全性ゲート |
| 回帰（静的ゲート） | 構造的欠落を検出 | T2 の logging、既存 F821 ゲート |

### 3.2 各タスクのテストケース（要約）

| タスク | 新規テスト | 種別 |
|---|---|---|
| T1 | `test_all_foreign_key_targets_are_registered` / `test_tenant_table_is_registered` | 結合 |
| T2 | `test_fileconfig_does_not_disable_existing_loggers` / `test_autouse_logger_disabled_guard_restores_state` | 回帰（静的） |
| T3 | `test_evict_if_needed_surfaces_executor_failure` / `test_run_io_works_after_shutdown` | 単体（契約） |
| T4 | （削除が正しい場合、追加なし。呼び出し元ゼロの静的確認のみ） | 静的 |
| T5 | `test_execute_rejects_raw_string` / `test_execute_accepts_text_clause` / `test_save_internal_state_select_patch_scope` / `test_create_snapshot_path_is_platform_neutral` | 単体（契約） |
| T6 | `test_check_and_resolve_marks_detected_foreshadowing` / `..._isolates_single_item_failure` / `..._distinguishes_contracted_from_uncontracted` | 単体（契約） |
| T7 | `test_trim_all_pinned_keeps_pinned_fact_intact` / `test_count_tokens_fallback_is_length_times_one_point_five` / `test_count_tokens_is_monotonic_in_both_backends` | 単体（契約） |
| T8 | `test_protocol_signature_matches_implementation` / `test_fetch_lastrowid_rejects_raw_string` | 単体（契約） |

### 3.3 リグレッション防止のため必ず遵守する原則

1. **期待値はハードコードしない**。実装の権威ある源（`resolve_spine`、`count_tokens`、
   `Base.metadata`）から導出する
2. **削除するテストはカバレッジを代替する新テストを必ず作る**（T6 が該当）
3. **順序依存を新たに作らない**。新規テストは単独でも緑であることを必ず確認する
4. **各タスクの後に `python scripts/ci_tier_ratchet.py` を実行**し、
   新規失敗ファイル Introduction がないことを確認する

### 3.4 各タスクの検証コマンド

```powershell
# 共通: 回帰ゼロの確認（新規失敗 Introduction がないこと）
python scripts/ci_tier_ratchet.py

# タスク別
python -m pytest tests/regression/test_v53_concurrent_transition.py -q      # T1: 単独で緑
python -m pytest tests/backend/test_metadata_completeness.py -q            # T1: 新規ゲート
python -m pytest tests/unit/core/test_core_without_plugins.py `
                 tests/unit/test_graphrag.py::test_graph_router `
                 tests/regression/test_v53_long_form_integrity.py -q        # T2: 最小再現が緑
python -m pytest tests/unit/test_marketing_agent.py `
                 tests/unit/test_semantic_cache.py -q                       # T3
python -m pytest tests/backend/test_database_core.py -q                     # T4/T5/T8
python -m pytest tests/services/ -q                                        # T6/T7
python -m pytest tests/regression -q                                       # 全回帰ゲート
```

---

## 4. 実行順序とチェックポイント

```
MS1: T1 → T2 → T3 → [ratchet 実行・確認]
       ↓ 停止条件: ratchet が緑
MS2: T5 → T6 → T7 → [ratchet 実行・確認]
       ↓ 停止条件: tests/backend と tests/services が緑
MS3: T4 → T8 → T10 → [ratchet 実行・確認]
       ↓ 停止条件: test_database_core.py 全体が緑
MS4: T12 → [ratchet 実行・確認]
       ↓ 停止条件: 順序依存テストが検出可能
MS5: T11（要判断）
```

---

## 5. 判断が必要な事項（実装前に合意したい）

| # | 判断事項 | 推奨 | 影響 |
|---|---|---|---|
| 1 | **T4**: `DatabaseConnectionWrapper` を復元 vs 削除 | **削除** | 60〜90行 vs 15行。`get_conn()` は deprecated で製品価値ゼロ |
| 2 | **T6**: `ForeshadowingResolutionStep` を実装 vs テスト削除 | **削除** | 「張った章＝回収した章」という誤仕様が製品に入り、既存 `check_and_resolve` と二重化するため |
| 3 | **T11**: `BookRepository` 重複の解消タイミング | 次イテレーション | 今回已完成済み（P2 相当） |
| 4 | **T12**: 順序依存テスト検出を strict にするか | **strict** | CI 時間が長くなるが、B2 の設計の穴を塞ぐ |

---

## 6. この計画が**しない**こと

| 提案 | 却下理由 |
|---|---|
| Tier1 の全失敗を一括で直す | 142 件中 43% は環境不在。本計画は P0/P1 の真正なものだけを扱う |
| `AUTH_DISABLED` の一括移行 | 前回 55 件を破壊した。`test_auth_bypass_contract.py` の xfail を残し、別途計画する |
| テストを大量に追加する | 検証力 lower bound を固定するのが本計画の方針。数ではなく検証の質 |
| `test_v53_concurrent_transition.py` の並列強度向上 | CAS の実装は正しい（`foreshadowing_repo.py:236-295`）。テストの自律性確保に絞る |

---

## 7. 工数サマリ

| 優先度 | タスク数 | 合計工数（行数目安） |
|---|---|---|
| P0 | 4 | 約 90〜135 行 |
| P1 | 5 | 約 105〜145 行 |
| P2 | 3 | 約 45〜70 行 + 判断 1 件 |
| **合計** | **12** | **約 240〜350 行** |

P0 の 4 タスク（計 3〜5 行 + 1 行 + 25〜40 行 + 15 行）を完了するだけで、
**ratchet が緑になり、残存 4 ファイルすべての failures を解消**できる見込み。