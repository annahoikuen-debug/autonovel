# PLAN_Q4-R: レビュー指摘是正 — 差分 P0 回復からゲート健全化まで (24 STEPS)

> **目的**: 2026-11-17 時点の 2 つのコードレビュー（①未コミット差分 79 ファイルの精査、②プロジェクト全体構造レビュー）で
> 検出した指摘を、**「先に赤ゲートを緑に戻し、次に偽の緑（無効な ignore・環境差）を除去し、最後に設計負債を整理する」**
> 順序で解消する。
>
> **対象ブランチ**: `fix/q1-red-gate-recovery`（HEAD `68137ce5`、**未コミット変更 79 ファイル / +200 -115**）
> **前提**: `PLAN_Q1`（ゲート緑化）〜 `PLAN_Q3`（shim 焼却）が完了済み。本計画は Q4 Phase 3（mypy バーンダウン）の
> 「速度優先で積んだ type-ignore・挙動変更」を対象にする。
> **作業方針**: 1 ステップ = 1 コミット。各 Phase は自分の検証コマンドが green になるまで次へ進まない（P5 継承）。
> **スコープ外**: 4 層アーキテクチャへの大規模再配置、`src/llm/unified` と `core/llm_gateway` の統合、
> conftest の DB フィクスチャ全面移行（Step 24 で持ち出し先を決定）。

---

## 0. 作業方針（判断基準）

| # | 原則 | 理由 |
|---|---|---|
| P1 | **「type: ignore で塞ぐ」は最終手段。まず `Optional`/プロトコル修正/実装修正を検討する** | 今回の 92 追加 ignore のうち 3 件は mypy エラーを**増やし**、3 件は**無効**、2 件は**不要**だった |
| P2 | **静的解析の改善は「clean checkout での再現」で検証する** | ローカルの残骸ディレクトリ（追跡ゼロの `__pycache__` のみ）により CI と 1 件差が出ることを実測済み |
| P3 | **テスト赤は「実装を直す or テストを直す」を必ず決めてから手を付ける** | `sd_client` は実装が正（`await time.sleep` はバグ）でテストが旧バグ前提、`rule_loader` はテストが正で実装変更が不要という**逆方向**の 2 種類が混在 |
| P4 | **型修正コミットに挙動変更を持ち込まない** | `prompt_registry` / `rag_service` / `narrative_scoring` / `vector_store.causes` / `semantic_cache` が型修正の裏で挙動を変えている |
| P5 | **各 Phase の検証コマンドが green になるまで次へ進まない** | 「動くはず」を確認しない |
| P6 | **ゲートの穴（CI 未搭載・部分一致黙殺・モック恒常化）は、機能修正と同時に塞ぐ** | 否则、同じバグが再び緑のまま通る |

---

## 1. Phase 0: ベースライン（実測・2026-11-17）

### 1-1. ゲート現状（すべて本セッションで実測）

| ゲート | 実測値 | baseline | 判定 |
|---|---|---|---|
| `ruff check src tests config scripts` | 0 | 0 | ✅ |
| `ruff format --check src` | 0 ファイル | 0 | ✅ |
| `ruff format --check tests config scripts` | **935 ファイル** | （対象外） | ⚠️ ゲート範囲外（Step 24） |
| `mypy src --ignore-missing-imports` | **250** / 120 files | 250 | ✅（ただし新規エラー3件を含む） |
| `pytest tests/unit` | **7743 passed / 12 failed** / 36 skipped | 0 failed | ❌ **全て本 diff 起因** |
| `pytest tests/regression/test_llm_unification_complete.py`（clean checkout） | **1 failed** | 0 failed | ❌ **CI 赤（実測再現）** |

### 1-2. mypy HEAD 比較（clean worktree で実測）

- HEAD: **365 errors** / 187 files → working tree: **250 errors** / 120 files（**-119 解消 / +4 新規**）
- 新規 4 件の内訳:
  1. `src/llm/unified/adapters/claude.py:113` `Invalid "type: ignore" comment [syntax]`
  2. `src/llm/unified/adapters/claude.py:128` 同上
  3. `src/llm/unified/adapters/ollama.py:115` 同上
  4. `src/engine/chunk_ingestion.py:10` `Module "src.services.vector_store" has no attribute ...`
     → **ローカル残骸ディレクトリ `src/services/vector_store/`（`__pycache__` のみ）由来の疑似エラー**。CI では発生しない（Step 12 で解消）

### 1-3. 失敗 12 件のAttribution（HEAD worktree で 31 件全パス → 因果確定）

| 原因（diff の 1 箇所） | 失敗テスト | 件数 |
|---|---|---:|
| `src/stores/vector_store.py:256-260` の bytes のみ対応 | `tests/unit/stores/test_vector_store.py` 6 + `tests/unit/pipeline/test_prompt_builder.py` 2 + `tests/unit/services/test_script_watcher.py` 1 | **9** |
| `src/publishing/illustration/sd_client.py` の `time`→`asyncio`（テストが旧実装前提） | `test_illustration_clients.py::TestSDWebUIClient` 2 | **2** |
| `src/rules/rule_loader.py:92` の `condition = _default_condition`（テストは `is None` を期待） | `test_rule_loader.py::test_load_rules_unknown_condition_unconditional` | **1** |

### 1-4. その他の確定事実

- `src/backend/database/uow.py:56` の新規 `commit()` は `retry_on_lock()(_commit_with_retry())` で **呼び出し毎に `TypeError: 'coroutine' object is not callable`**（実測）。`await self.uow.commit()` は `src/application/use_cases/*` に 20 箇所以上。テストが盲点な理由は `uow=AsyncMock()` 依存。
- `tests/regression/test_llm_unification_complete.py:40-50` は追跡ゼロの `src.core.llm` 等を例外なしで import → clean checkout で必ず `ModuleNotFoundError`。CI は `ci.yml:154` で `pytest tests/regression/` を実行するため赤。
- `tests/conftest.py:396` は `if "age_client" in lowered` の**部分一致**で収集黙殺（同ファイル 325-380 に過去インシデントの反省文あり）。
- `scripts/check_layer_boundaries.py` は `Makefile:27` のみで **CI 未搭載**（`docs/architecture/layers.md:82` の記述と乖離）。
- `tests/conftest.py:298-319` の autouse モックにより **CI は実 LLM アダプタ経路を一度も検証していない**。
- `src/rules/emotional_rules.py:86-96` の `evaluate()` は `condition is None` を「常に適用 (True)」と明文支持 → `rule_loader` の `_default_condition` 差入はランタイム不要（型の問題だけ）。

---

## 2. Phase 1: 赤ゲート回復 — 差分 P0 (Steps 1-7)

### Step 1: `UnitOfWork.commit()` の TypeError 修正 + `__aexit__` 共通化

**対象**: `src/backend/database/uow.py`

**変更**:
```python
# 修正前 (uow.py:56)
await retry_on_lock()(_commit_with_retry())     # コルーチンを「関数」として渡す → TypeError

# 修正後
await retry_on_lock()(_commit_with_retry)()     # デコレータ適用 → ラッパーを呼ぶ
```

あわせて:
1. `commit()` を `__init__` の**後**（`__aenter__` の近く）へ移動（現在は class docstring 直下 `__init__` より上に定義されて可読性が悪い）。
2. `__aexit__` 内の `_commit_with_retry` 定義と 232 行目の呼び出し（正しい形）を、`commit()` 本体に集約して
   `__aexit__` は `await self.commit()` のみ呼ぶ（**現在のロジック重複を除去**）。
3. `commit()` 内の `raise RuntimeError("Session is None during commit")` は `__aexit__` と同メッセージのまま維持（既存テストのメッセージ依存を確認）。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/database/test_uow.py tests/unit/database/test_uow_integration.py tests/unit/database/test_uow_context.py -q --timeout=60
```
**受け入れ基準**: 上記 green（現状も green なので、**Step 2 の新テストが追加で green であること**が有効性の証明）。

---

### Step 2: 実実装を使う `commit()` 回帰テスト新設

**対象**: 新規 `tests/unit/database/test_uow_commit.py`

**理由**: `tests/unit/application/*` は `uow=AsyncMock()` のため実 `commit()` が一度も実行されず、Step 1 相当のバグが通り続けた。

**実装方針**:
- `aiosqlite` のファイル/メモリ DB で `DatabaseManager` を組み、`UnitOfWork(db=...)` を `async with` で開く。
- `stage_chroma_add()` で 1 件ステージ → `await uow.commit()` → **`session.commit()` 済みであること**（`session.in_transaction() is False`）と outbox 行が 1 件 INSERT されていることを assert。
- ロック再試行パスの単体テスト: `retry_on_lock` にダミーの `OperationalError("database is locked")` を 1 回だけ投げさせるモック注入で「リトライ後成功」を assert（コルーチン再利用による `RuntimeError: cannot reuse` が出ないこと）。
- **キャンセル/例外時**: `commit()` が例外を握りつぶさないこと。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/database/test_uow_commit.py -q --timeout=60
```
**リスク**: outbox flush が Chroma を触る可能性 → `ChromaOutboxService.flush` を差し替えて DB のみで完結させる（ステージ 0 件なら flush が DB に書き込むだけ、という既存実装を Step 中に確認し、必要なら skip 条件を明記）。

---

### Step 3: `get_namespace_keys` の str/bytes 両対応（9 テスト回復）

**対象**: `src/stores/vector_store.py:253-262`

**変更**:
```python
cursor, batch = self.client.scan(cursor, match=pattern, count=100)
prefix = f"emotional:{namespace}:"
for k in batch:
    key = k.decode() if isinstance(k, bytes) else k   # decode_responses 有無の両対応
    if key.startswith(prefix):
        keys.append(key[len(prefix):])
```

**根拠（P3）**: 現行 `if isinstance(k, bytes)` は `decode_responses=True`（str 返却）で全スキップ → `get_latest` / `get_all` も連鎖全滅。旧実装は bytes クライアントで `TypeError`、新実装は str クライアントで空振りという**片側破壊の入れ替え**だった。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/stores/test_vector_store.py tests/unit/pipeline/test_prompt_builder.py tests/unit/services/test_script_watcher.py -q --timeout=60
```
**受け入れ基準**: 9 件 green。**追加で** `fakeredis.FakeRedis()`（bytes 返却・`decode_responses=False`）の 1 ケースを `test_get_namespace_keys` にパラメタ化追加し、**両モードを固定**する。

---

### Step 4: `sd_client` テストの patch 対象を `asyncio.sleep` へ（2 テスト回復）

**対象**: `tests/unit/publishing/illustration/test_illustration_clients.py:597, 617`

**変更**:
```python
# 修正前
monkeypatch.setattr("src.publishing.illustration.sd_client.time.sleep", AsyncMock())
# 修正後
monkeypatch.setattr("src.publishing.illustration.sd_client.asyncio.sleep", AsyncMock())
```

**判断記録（P3）**: 実装側の `await time.sleep(...)` → `await asyncio.sleep(...)` は**正しいバグ修正**（`time.sleep` は await 不可）。よって直すのはテスト。変更コメントに「旧実装は `await time.sleep` というバグだった。テストが旧バグの patch 対象を前提にしていた」と明記。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/publishing/illustration/test_illustration_clients.py -q --timeout=60
```

---

### Step 5: `rule_loader` の `condition` を `Optional[Callable]` へ（1 テスト回復 + ignore 2 件削除）

**対象**: `src/rules/emotional_rules.py:62` / `src/rules/rule_loader.py:13, 92, 101`

**判断（P3）**: `EmotionalRule.evaluate()`（`emotional_rules.py:86-96`）は **`condition is None` を「常に適用 True」と明文サポート**。したがって:

1. **`rule_loader.py` の差分を revert**（`condition = _default_condition` と `from src.rules.emotional_rules import _default_condition` を撤去、`condition=condition` の ignore も撤去）。
2. `emotional_rules.py` の型を実態に合わせる:
   ```python
   condition: Callable[[PlotContext], bool] | None = field(default=_default_condition)
   ```
3. `rule_loader.py::_build_rule` 冒頭を `condition: Callable[[PlotContext], bool] | None = None` に変更。
4. private `_default_condition` を外部から import しない（**現状 diff は private シンボルへの依存を生んでいる**）。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/rules/ -q --timeout=60
.venv/bin/python -m mypy src/rules --ignore-missing-imports
```
**受け入れ基準**: `test_load_rules_unknown_condition_unconditional` green、`src/rules` の mypy エラーが diff 前以下。

---

### Step 6: `editorial_assistant_service` の `join(SearchResult)` 修正 + 回帰テスト

**対象**: `src/services/editorial_assistant_service.py:49-50, 144-151`

**変更**:
```python
# 修正前（実行時 TypeError: sequence item 0: expected str instance, SearchResult found）
evidence_text_parts.append("【過去章・設定抜粋】\n" + "\n---\n".join(similar_chunks))  # type: ignore[arg-type]

# 修正後
evidence_text_parts.append(
    "【過去章・設定抜粋】\n" + "\n---\n".join(c.content for c in similar_chunks)
)
```
- ignore は撤去。`_retrieve_evidence` 内の `raw_neighbors = self.rag.get_graph_context(...)` は **sync 実装**であることをコメントで明記（`rerank_graph_neighbors` のみ await 対象、という非対称が誤解を招く）。
- テスト: `tests/unit/` に `EditorialAssistantService.ask_bible` のテストを新設。`rag.search_similar_chunks` を `SearchResult` 2 件の coroutine で mock し、**例外なく回答が返ること**を assert（現在この経路は未検証）。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/test_editor_models.py tests/unit/test_editorial_assistant*.py -q --timeout=60
```

---

### Step 7: Phase 1 ゲート — ここで 1 コミット

```bash
.venv/bin/python -m ruff check src tests config scripts
.venv/bin/python -m ruff format --check src
.venv/bin/python -m mypy src --ignore-missing-imports   # 250 以下を維持（Step 5 で -2 程度減る想定）
timeout 3000 .venv/bin/python -m pytest tests/unit -q --timeout=120   # 0 failed
```
**受け入れ基準**: unit **0 failed**（12 件全回復）。`config/ci_lint_baseline.json` はこの時点では触らない（Step 12 で一括更新）。
**コミット**: `fix(plan-q4 R): レビュー P0 修復 — uow.commit TypeError / vector_store str+bytes / ignore 実装化（unit 12 failed→0）`

---

## 3. Phase 2: 型ゲートの健全化 — 無効・不要 ignore の除去 (Steps 8-12)

### Step 8: 独立行 `# type: ignore` 6 件の撤去と実修正

**対象と対応**:

| 場所 | 現状 | 実修正 |
|---|---|---|
| `src/llm/unified/adapters/claude.py:113` | 独立行 ignore → **mypy が `Invalid "type: ignore"` エラーを出す** | ignore 削除。`stream()` の `raise NotImplementedError` は正当なので、該当エラーが [unreachable] なら `if TYPE_CHECKING:` ではなくコメントで方針整理、実エラーが残る場合のみ行末 ignore に再配置 |
| `src/llm/unified/adapters/claude.py:128` | 同上（`stream.stop_reason`） | Anthropic SDK 型の実測に従い `getattr(stream, "stop_reason", None)` に置換して ignore 廃止 |
| `src/llm/unified/adapters/ollama.py:115` | docstring 行への ignore → **`Invalid` エラー化** + 元の [override] も未解消 | **interface 側を直す**: `src/llm/unified/interface.py:35` の `async def astream(...) -> AsyncIterator[...]` は型としては `Coroutine[Any, Any, AsyncIterator[...]]` となり、async generator 実装（4 アダプタ全て）と不一致。**`async` を外して `def astream(...) -> AsyncIterator[StreamChunk]` にする**（mypy の note「Consider declaring 'astream' in supertype without 'async'」どおり）。4 アダプタの override エラーが同時に消える |
| `src/integrations/rag/reflective_rag.py:504, 519, 540` | 独立行 ignore は**無効**（エラーは 505/520/541 に残存、実測） | `session: Session` の narrowed 変数受け渡し（`Session | AsyncSession` の分岐）に修正。`iscoroutine` 手動判定は残すが mypy 向けに `cast` を使う |
| `src/services/plot_service.py:15, 29` | 独立行 + 行末 ignore | **不要**（当該ファイルにエラーなし、実測）。両方削除 |

**検証**:
```bash
.venv/bin/python -m mypy src --ignore-missing-imports | tee /tmp/mypy_s8.txt
grep -c 'Invalid "type: ignore"' /tmp/mypy_s8.txt   # → 0
```
**受け入れ基準**: `Invalid "type: ignore" = 0`、総数が Step 7 以下。

---

### Step 9: `x: T = None` を ignore で塞いでいる箇所を `Optional` 化

**対象**:
- `src/narrative_balancer/arbitrator/ports.py:26, 77, 147` → `balancer: DSPTensionBalancer | None = None`（等、3 クラス）
- `src/publishing/illustration/base.py:24` → `metadata: dict | None = None`
- `src/narrative_balancer/csp/cli.py:26` → `argv: List[str] | None = None`
- `src/agents/social/friends_discovery.py:120-122` → 注釈追加済みなので行末 ignore 3 件を**削除して誤りがないか実測**（未使用 ignore かもしれない）

**同 diff 内の正の見本**: `src/domain/services/cost_analytics.py`（`Optional[str]`）、`src/models/audit.py`（`Optional[dict]`）は正しく実装されている。これをスタイル基準にする。

**検証**: 上記ファイル単位の mypy + ruff。

---

### Step 10: `IRepository` プロトコルと実装のシグネチャ不一致を解消

**対象**: `src/core/interfaces.py:156`（`get_plot(self, branch_id, ep_num, book_id=None)`） vs `src/infrastructure/repositories/plot.py:24`（`get_plot(self, book_id_or_branch_id, ep_num, branch_id=None, book_id=None)`）、および `src/backend/database/repo_protocols.py:10` の `update_plot_blueprint`

**変更**: プロトコル側を実装に合わせる（第 1 引数名を `book_id_or_branch_id`、`branch_id` キーワード引数を追加）。`src/services/plot_service.py:14-16` のコメントに書かれている「IRepository has duplicate branch_id keyword」＝**型エラーで検知された設計不整合**を実体修正で解消し、ignore 2 件を撤去。

**検証**:
```bash
.venv/bin/python -m mypy src/services/plot_service.py src/core/interfaces.py --ignore-missing-imports
.venv/bin/python -m pytest tests/unit -q -k "plot" --timeout=120
```
**リスク**: Protocol 変更は具象リポジトリへの波及を伴う → `grep -rn "get_plot(" src` で全呼び出しを列挙し、位置引数の意味が変わらないことを確認（`plot_service.py:14` は位置引数で第 1 引数を `book_id`/`branch_id` の両義で使っている点を明確化するコメントを追加）。

---

### Step 11: `warn_unused_ignores` の導入可否を実測して決定

**手順**:
```bash
# 1) 追加で発生する「未使用 ignore」件数を実測（この値が導入コスト）
.venv/bin/python -m mypy src --ignore-missing-imports --warn-unused-ignores 2>&1 | grep -c "unused.*type: ignore"
# 2) 100 件未満なら Phase 完了時に有効化、500 件超なら「モジュール単位 ratchet」に切り替え
```
**追加ゲート（无论如何に設ける）**: `scripts/ci_lint_ratchet.py` に `invalid-ignore` カウンタを追加し、`Invalid "type: ignore" comment` が **1 件でも増えたら fail**（baseline: 0）。現在の ratchet は総数しか見ないため、**「ignore を増やしてエラーを増やす」再発を検知できない**。

**受け入れ基準**: ratchet に新カウンタが実装され `--tool all` が green。

---

### Step 12: baseline 整合 + ローカル/CI 環境差の解消

1. **残骸ディレクトリ削除**（追跡ゼロ・`__pycache__` のみ）:
   ```bash
   # 該当の全調査（実測で 3 箇所確認済み）
   git ls-files src/core/llm src/core/llm_clients src/services/llm src/services/vector_store | wc -l  # → 0
   rm -rf src/core/llm src/core/llm_clients src/services/llm src/services/vector_store
   ```
   ⚠️ Step 13 のテスト修正と**同コミット**で行う（削除すると Step 13 修正前のテストが落ちる）。
2. **baseline 更新**: Phase 1-2 完了後の実測値で
   ```bash
   .venv/bin/python scripts/ci_lint_ratchet.py --tool mypy --update
   ```
3. **history 注記の整合**: `config/ci_lint_baseline.json` の history に `304`（2026-11-17 記載）と top-level `250` が同日で不整合 → 同日複数エントリにするか注記を実測値に修正。
4. **CI/ローカル parity の恒久確認**: `make verify` 相当の手順に「clean worktree での mypy 実測」を含める（P2）。最小構成では `scripts/check_migrations.py` と同じ呼び出し位置に追加。

**検証**: clean worktree（`git worktree add` + `config/settings.toml` コピー）で
```bash
.venv/bin/python -m mypy src --ignore-missing-imports   # ローカルと同値であることを確認
```

---

## 4. Phase 3: CI・テストゲートの穴を塞ぐ (Steps 13-17)

### Step 13: clean checkout 必落ちテストの修正

**対象**: `tests/regression/test_llm_unification_complete.py:40-50`

**変更**:
```python
# 修正前
mod = importlib.import_module(module_path)          # ModuleNotFoundError で落ちる
assert not hasattr(mod, "LLMProviderFactory")

# 修正後
with pytest.raises(ModuleNotFoundError):
    importlib.import_module(module_path)            # 空/削除済みパッケージは「不在」であるべき
```
さらに各シンボルが**どの新パスで公開されているか**の positive assert を残す（削除だけを検証するテストは新しい実体の退行を見逃す）。

**検証（必須: clean worktree で）**:
```bash
git worktree add /tmp/opencode/verify HEAD
cp config/settings.toml /tmp/opencode/verify/config/
cd /tmp/opencode/verify && /home/annahoikuen/autonovel/.venv/bin/python -m pytest tests/regression/ -q --timeout=120
```
**受け入れ基準**: 現在 **1 failed（実測）** → green。

---

### Step 14: 「追跡ゼロのパッケージを import するテスト」の機械スキャンを導入

**理由**: Step 13 は 1 件の症状。同型（`git ls-files` 0 件なのに import する）が他にない保証がない。

**実装**: `scripts/check_untracked_imports.py`（新規）
- `git ls-files -- '*.py'` で追跡集合を取得
- `tests/**/*.py` から `importlib.import_module` / `from X import` の文字列リテラルを抽出
- 「存在するパッケージパスだが追跡 .py が 1 もないもの」を報告 → exit 1
- **CI**: `ci.yml` の static-analysis job に step 追加。既知 3 箇所は Step 12 で消えているので 0 件が green 条件。

**検証**: ローカルで 0 件（Step 12 完了後）、故意に残骸を作って 1 件検出されることをデモ。

---

### Step 15: conftest の部分一致収集黙殺を完全一致へ

**対象**: `tests/conftest.py:395-397`（および `409-412` の skip 側も同じ式）

**変更**:
```python
# 修正前（"storage_client" "message_client" 等も黙殺しうる）
if "age_client" in lowered:
    return True
# 修正後
rel = _rel_path(collection_path)
if rel.startswith("tests/") and Path(rel).name.startswith("test_age_client"):
    return True
```
- あわせて `pytest_collection_modifyitems` の収集件数を記録: 現行 **10703 collected（過去記録）/ unit 7743+12+36+9** を `config/test_collection_baseline.json` に保存し、**収集数の減少を ratchet で検知**する（黙殺の再発防止。`tests/conftest.py:325-380` の反省文どおりの機構化）。

**検証**: `pytest --collect-only -q | tail -1` が baseline 以上。

---

### Step 16: レイヤー境界チェックを CI に搭載

**対象**: `.github/workflows/ci.yml`（static-analysis job）+ `Makefile:27` + `docs/architecture/layers.md:82`

**変更**: `python scripts/check_layer_boundaries.py` を ratchet と並列 step として追加。docs の「CI で落ちる」記述と実態を一致させる。

**検証**: PR で step が走ることを確認。ローカル `make lint-layers` green 維持。

---

### Step 17: CI の検証漏れ 2 件（`|| true` と実アダプタ未検証）

1. **`.github/workflows/ci.yml:230` の `|| true` 削除**
   ```yaml
   pip install -e .. || pip install -r ../requirements.txt || true   # 修正前
   pip install -e .. || pip install -r ../requirements.txt           # 修正後（失敗で落とす）
   ```
2. **実アダプタ経路の検証**: `tests/conftest.py:298-319` の autouse モックは残しつつ、**integration job のみ** `TEST_WITH_REAL_LLM=1` + `real_llm` マーカーテストを実行（HTTP 層は mock transport：既存 `tests/unit/test_openai_adapter.py` 等のモック方針に合わせる）。
   - 最小版: `pytest -m real_llm tests/integration --timeout=120` を CI に追加し、0 件なら「マーカー付きテストが 0 件」として fail させる（スイープを防ぐ）。
   - 件数が 0 の場合 Step 内で最低 1 件（openai adapter の疎通）を追加するか、job を `continue-on-error: false` で止めず段階導入するかを**判断記録を残して**選ぶ。

**検証**: CI 実行で両 step が green。

---

## 5. Phase 4: 型修正に隠れた挙動変更の分離 (Steps 18-21) — P4

各 Step は「**元に戻す**」か「**意図として明文化しテストで固定する**」の 2 択を必ず記録する。

### Step 18: `PromptRegistry` のキャッシュと `""` 返却

**対象**: `src/services/prompt_registry.py:17, 33-48`

**事実**:
- `disable()` 時にテンプレート未キャッシュなら `""` を返す（従来は必ず render）。メトリクス停止機能が「空プロンプト生成機能」に化けている。
- `_templates` キャッシュに無効化経路がなく、プロンプト更新がプロセス生存中に反映されない。
- 現状 `PromptRegistry.disable()` の呼び出しは src/tests に**存在しない**（dead path）。

**推奨**: **revert**（`disable` 時も `self._pm.get_template(...).render(...)` を呼ぶ）。キャッシュを残す場合は `PromptManager` 側の再読込 API と連動する `invalidate(template_name)` を追加し、`tests/unit/test_prompt_registry.py` に「disable 後もレンダリングされる」「テンプレート更新が反映される」を追加。

**検証**: `pytest tests/unit/test_prompt_registry.py tests/promptops/ -q`

---

### Step 19: falsy チェーンと `None`→`""` 契約

1. **`src/services/narrative_scoring_service.py:29-31`**
   ```python
   # 修正前（score=0 が 75.0 に化ける）
   float(metadata.get("score") or result.get("score") or 75.0)
   # 修正後
   score = metadata.get("score", result.get("score", 75.0))
   score_val = float(score) if score is not None else 75.0
   ```
   テスト: `score=0` を返す mock で **0 のまま**であることを固定（新規 1 件）。
2. **`src/stores/vector_store.py:92, 212`（`causes.get(key) or ""`）**: None→"" の変換は `src/backend/routers/annotations.py:175,196` の API 返却（`null` → `""`）と `src/pipeline/emotional_residue.py:95`（None を返す）で**契約が分裂**した。決定: API が `""` を返す契約なら `EmotionalResidue.get_cause()` も `or ""` に揃え、`"cause" in response` の契約テストを 1 件追加。None 維持が正なら `stores/vector_store.py` 側を戻し型を `dict[..., str | None]` にする。

**検証**: `pytest tests/unit/test_vector_store.py tests/unit/services/test_vector_store_deep.py tests/unit -k "annotation or cause" -q`

---

### Step 20: `GraphRAGService` の eager 初期化

**対象**: `src/integrations/rag/rag_service.py:70-93`

**事実**: `__init__` で `get_default_store()` を即時構築（明示モードでは例外送出・接続オブジェクト生成）。getter の `if self._vector_store_instance is None` は事実上死に、setter の else 系は instance を更新しない。

**推奨**: **lazy に戻す**（`self._vector_store_instance = None` + getter での初回生成、 setter は両方を更新）。挙動変更は「生成時の例外をコンストラクト時点へ移動した」ことを含み、`tests/unit/test_rag_service.py` に「store 非指定でコンストラクトしても store が生成されない」を追加。

**検証**: `pytest tests/unit/test_rag_service.py tests/unit/test_reflective_rag*.py -q`

---

### Step 21: semantic cache プリフェッチの鍵一致を保証

**対象**: `src/integrations/semantic_cache.py:387-431`

**事実**: プリフェッチは `build_drafting_prompt` の **user 部分（`prompt[1]`）** で `_get_l1_key` を作る。実検索側（`PromptCacheService.get` → `semantic.search(prompt=...)`、`src/services/redis_cache.py:478`）が渡す文字列と一致する保証を示すテストが存在しない。不一致ならプリフェッチ（embedding 計算・バックタスク投入）は完全な無駄。

**実装**:
1. 呼び出し側（`src/backend/workflows/episode_writing_workflow.py` 経由）が実際に渡す文字列の型を特定（`grep -rn "get_cached_response(" src`）。
2. 一致することを**回帰テスト**で固定: user prompt で `prefetch_next()` → 同一文字列で `search()` が L1 hit すること。
3. 不一致なら「プリフェッチ対象キーの生成を実検索と同一ヘルパーに集約」して修正。
4. あわせて polishing 系の `# type: ignore[assignment]` / `prompt[1]` と `isinstance(prompt, str)` の二重分岐（`semantic_cache.py:404-425`）を、`prefetch_prompts: list[tuple[str, str]]` に正規化して整理。

**検証**: `pytest tests/unit/test_semantic_cache.py tests/unit/workflows/test_episode_writing_prefetch_wiring.py tests/contract/test_w6_prefetch_invalidation_wiring.py -q`

---

## 6. Phase 5: 計画・負債の整合 (Steps 22-24)

### Step 22: `PLAN_Q3` Step 9/10 と実コードの乖離を解消（意思決定必須）

**事実（レビュー実測）**:
- 計画は `src/llm/service.py` / `src/models/db.py` の削除を規定 → 実際は両方とも現存。`src/llm/service.py` は docstring で「PLAN_Q3: 旧 shim から正規モジュールに昇格」と宣言（**方針変更が計画側に未反映**）、15 ファイルが依存。
- `src/models/db.py` は `src/domain/models/chapter.py:12` と `ChapterDbModel` を**二重定義**、本番 5 ファイル（`src/core/interfaces.py:9`、`src/backend/engine_plot.py:18` 等）が旧側を使う。

**選択肢と推奨**:
- A（推奨・小）: `PLAN_Q3_SHIM_BURNDOWN_16STEPS.md` の Step 9/10 を「昇格完了・維持」に**改訂**し、二重定義だけ新パス統一へ（本番 5 ファイルの import 先を `src.domain.models` に切り替え + DeprecationWarning ゲート）。
- B（大）: 計画どおり削除を完遂（15 ファイルの参照解消）。

**検証**: `pytest tests/unit -k "model or chapter" -q` + `python scripts/check_layer_boundaries.py`

---

### Step 23: デッドコード 3 点の整理

1. `src/llm/clients/base.py:8-44` の `BaseLLMClient`（実装クラス 0・参照は再エクスポートのみ）を削除し、`tests/regression/test_llm_unification_complete.py:22` の positive assert を外す。
2. `src/llm/clients/__init__.py:3-5` の**自己参照 docstring**（「統合先: src/llm/clients/」）を削除。
3. `tests/regression/test_shim_imports.py:24` のコメントアウト残骸を削除。
4. （参考）`src/models/db.py:142-147` の dict 風 `get()` フックは Step 22 の選択肢に依存 → 参照ゼロを確認のうえ削除。

**検証**: `pytest tests/regression/ -q --timeout=120`（clean worktree 含む）

---

### Step 24: ゲート範囲・設計課題の処理方針を決定して持ち出し記録

| 課題 | 現状 | 判断（記録を残して選ぶ） |
|---|---|---|
| format ゲート範囲 | `src` のみ 0 / `tests+config+scripts` **935 ファイル未整形** | (a) `ruff format` を tests に一括適用 + ゲート拡張（diff 膨大）、(b) 範囲を明文化して現状維持、のどちらか。**放置が最悪** |
| `tests/conftest.py:116-209` のグローバル monkeypatch DB フィクスチャ | 並列実行で競合し得る | `dependency_overrides` 移行を次計画（PLAN_Q4-R2）へ持ち出し。本計画では `pytest-xdist` 導入可否の判定材料として収集時間を記録 |
| `pytest.ini:27` の `flaky` マーカー | `rerunfailures` 未導入で記録のみ | 未導入ならマーカー削除、導入なら `--reruns` を CI に追加 |
| lint 債務の ratchet 単位 | 総数のみ（モジュール級の劣化が見えない） | Step 11 の `invalid-ignore` カウンタと合わせ、次段階として「モジュール別 count の top-N 常時表示」を追加 |

**持ち出しドキュメント**: `plans/` に `PLAN_Q4_R2_BACKLOG.md` を作成し、上記 4 件と Phase 5 で「実装しない」を選んだ項目を記録する。

---

## 7. ゲート一覧と Definition of Done

### 各 Phase 完了条件

| Phase | 検証コマンド | 受け入れ基準 |
|---|---|---|
| P1 (Step 7) | `pytest tests/unit -q --timeout=120` | **0 failed**（12→0） |
| P2 (Step 12) | `mypy src` + `ruff format --check src` + clean worktree mypy | mypy ≤ 250、`Invalid "type: ignore"` = 0、ローカル=CI 同値 |
| P3 (Step 17) | clean worktree で `pytest tests/regression/ -q` + CI 実行 | **0 failed**（1→0）、境界チェック step が CI に存在 |
| P4 (Step 21) | 各対象テスト + `pytest tests/unit` | 0 failed、挙動変更の各項目に「revert or 意図+テスト」の記録がある |
| P5 (Step 24) | `make verify` | green、持ち出し backlog 作成済み |

### 最終 DoD（チェックリスト）

- [ ] `pytest tests/unit` 0 failed（現状 12 failed）
- [ ] clean checkout で `pytest tests/regression/` 0 failed（現状 1 failed）
- [ ] `UnitOfWork.commit()` が実実装テストで検証されている（AsyncMock 依存の排除）
- [ ] `mypy`: `Invalid "type: ignore" = 0`（現状 3）+ ratchet に新カウンタ
- [ ] 独立行 `# type: ignore` 9 件が全て「実修正 or 削除」されている
- [ ] 挙動変更 6 箇所（prompt_registry / narrative_scoring / causes / rag_service / semantic_cache / editorial）が「revert or 意図+テスト」で処理済み
- [ ] CI: レイヤー境界チェック追加、frontend `|| true` 削除、収集黙殺の完全一致化
- [ ] `PLAN_Q3` Step 9/10 の乖離について計画改訂 or 実行を選択し記録
- [ ] clean worktree で mypy / ruff / format がローカルと同値

### コミット規約

1 ステップ = 1 コミット。件名は `fix(plan-q4-R StepN): <内容>（<計数変化>）`。
Phase 完了ごとに baseline JSON を更新し、**baseline 更新は機能コミットと分離**する（差分レビューで歴史注記の不整合が生じたため）。

### リスクとロールバック

| リスク | 緩和 |
|---|---|
| Step 10（Protocol 変更）が全リポジトリに波及 | 変更前に `grep -rn "get_plot\|update_plot_blueprint" src` で呼び出し全列挙。位置引数の意味確認を必須に |
| Step 11 の `warn_unused_ignores` 導入でエラー洪水 | 実測件数 → しきい値判断を Step 内に明記。即時有効化しない |
| Step 17 の `|| true` 削除で frontend job が赤に | 依存導入の失敗理由を先に特定してから削除（順序を Step 内で分離） |
| 並行セッション・外部コミットとの衝突（過去実績あり） | commit 前に `git status` / `git log -3` / `tests/unit/config/test_public_api.py` を実行（PLAN_SECURITY_GATE_AND_DEBT P4 継承） |
