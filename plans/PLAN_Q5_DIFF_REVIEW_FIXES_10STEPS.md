# PLAN_Q5: 差分レビュー残指摘の是正 — H/M/Low 指摘と pre-existing の切り分け (10 STEPS)

> **目的**: `fix/q1-red-gate-recovery` ブランチの 4 コミット差分（`68137ce5..79e389b5`）に対する
> 差分レビューで残った指摘（H-1 / H-2 / M-1 / M-2 / Low 群）を是正する。
> **本計画の特徴**: 全指摘について clean checkout / base worktree での**決定的実測を完了済み**であり、
> 各ステップは推測ではなく実測値を根拠に実装する。pre-existing（本差分に起因しない赤）は
> **修正せず「修正提案付きで報告」**し、ユーザーの判断に委ねる（Phase D）。
>
> **対象ブランチ**: `fix/q1-red-gate-recovery`（HEAD `79e389b5`、ワークツリークリーン）
> **前提**: `PLAN_Q4_REVIEW_REMEDIATION_24STEPS.md` が完了済み（4 コミット: `2020b421` / `6773dbad` / `30b6870c` / `79e389b5`）。
> **作業方針**: 1 ステップ = 1 コミット。各 Phase は自分の検証コマンド green まで次へ進まない（P5 継承）。
> **スコープ外**: Phase D の pre-existing 4 項目の実修正（ユーザー判断後に別計画へ）。
>
> **実測根拠の保管場所**:
> - clean collect: `/tmp/opencode/clean_collect_full.txt`（9331 / 86 errors）
> - base collect: `/tmp/opencode/base_collect_full.txt`（9324 / 86 errors）
> - HEAD collect: `/tmp/opencode/main_collect_full.txt`（9767 / 0 errors）
> - test ID 差分: `/tmp/opencode/main_ids.txt` / `clean_ids.txt` / `lost_ids.txt`（436 件）
> - mypy 2 回実行: `/tmp/opencode/mypy_run1.log` / `mypy_run2.log`

---

## 0. 作業方針（判断基準）

| # | 原則 | 理由 |
|---|---|---|
| P1 | **「type: ignore で塞ぐ」は最終手段。まず narrowing / 実装修正を検討する** | 今回も ignore 4 件のうち 3 件は「エラーが消えた後の残骸」、1 件は「塞ぐエラーと別コード」だった |
| P2 | **静的解析・収集の検証は clean checkout で行う** | ローカルは `config/settings.toml`（gitignore 対象）と path hook のリークがあり CI と結果が異なる |
| P3 | **pre-existing は「証拠（base でも同一）」を取ってから報告する** | base worktree `68137ce5` で再実測し、本差分の責任と切り分ける |

---

## 1. 実測サマリー（本計画の全根拠）

### 1.1 collection の三者比較（決定的実測）

| 環境 | collected | errors | エラー内容 |
|---|---|---|---|
| HEAD ローカル | **9767** | 0 | — |
| HEAD clean checkout | **9331** | **86** | 全件 `FileNotFoundError: config/settings.toml` |
| base `68137ce5` clean checkout | **9324** | **86** | **エラーファイル集合が HEAD clean と完全一致（`diff` 空）** |

- 失われた test ID = **436 件**、そのファイル集合（86 件）と ERROR ファイル集合（86 件）が**完全一致**。
- `scripts/check_test_collection.py` は clean で `actual=9331 baseline=9766` → **exit 1**（CI collection ゲートが clean で確実に赤）。
- **base でも同一の 86 errors** → **全件 pre-existing**（本差分の責任ではない）。
- 原因: `config/settings.toml` は `.gitignore:13` 対象で、`GlobalConfigModel.load()` が
  `validate_all(strict=True)` の前に `FileNotFoundError` を送出。workflows に生成ステップなし。

### 1.2 mypy 二重実行の実測（M-1 の根拠）

| コマンド | 時間 | 件数 | invalid-ignore |
|---|---|---|---|
| `mypy src` | 8.1s | 235 | 0 |
| `mypy src --ignore-missing-imports` | 7.7s | 235 | 0 |

- 両者**出力同一**。根拠: `pyproject.toml` `[tool.mypy] ignore_missing_imports = true`（line 239）。
- 結論: `--ignore-missing-imports` は**現設定下で無意味なフラグ**。2 プロセスは合計 ~16 秒の無駄。

### 1.3 H-2 の AST 解決プロトタイプ（有効性実証済み）

- `importlib.import_module(変数)` を「module-scope 代入リテラル + `@pytest.mark.parametrize` 経由」で解決する AST 解析を試作。
- 結果: **解決 67 件 / 欠落 2 件 / 誤検出 0**。欠落 2 件は `src.api.health` と
  `src.services.llm.circuit_breaker` ＝ **H-1 の対象と完全一致**。
- **不採用案**: 全 `src.` 文字列リテラルの素朴走査 → **548 件誤検出**（`patch()` 対象の属性パス
  `src.backend.observability.health.check_database` 等が混在するため）。この案は採らない。

### 1.4 不要 ignore の実測（Low 群の根拠）

| ファイル:行 | HEAD の ignore | 実測（通常モード mypy） | base の状態 | 判定 |
|---|---|---|---|---|
| `proposal_isolation.py:94` | `[index,assignment]` | **エラー無し（unused）** | 同 | 撤去 |
| `proposal_isolation.py:96` | `[assignment]` | **実エラー `[index]` が残存**（ignore は別コードを塞いでいる） | 同位置に `[index]` 実エラー | **移設ではなく narrowing 実修正を検討** |
| `proposal_isolation.py:97` | `[assignment]` | エラー無し（有効） | base では実エラーあり | 維持 |
| `judge_panel.py:392,395` | `[assignment]` | **エラー無し（不要）** | base では line 394 に arg-type 実エラー → lambda 化で消滅 | 撤去 |
| `nlp/japanese_tokenizer.py:146` | `[arg-type]` | **エラー無し（不要）** | base では attr-defined 実エラー → assert narrowing で消滅 | 撤去 |

### 1.5 M-2 の実測

- `src/services/prompt_registry.py` の本番 importer（`src` / `tests` 内、対象ファイル除く）**0 件**。
- `PromptRegistry` が参照する `PromptManager.get_template` は `prompts/manager.py` に**不存在**（`rc=1`）。
  → `prompt_registry.py:33,37` の mypy attr-defined エラーは **base でも存在（pre-existing）**、
  つまり**動作していないコード**。
- `PromptRegistry.invalidate()` の呼び出し元 **0 件**。テストは `tests/unit/test_prompt_registry.py`
  4 件のみ（全件 MagicMock、`get_template` を直接スタブ）。
- → 「削除」か「実装修復」の判断を Phase B Step 5 で提示する。

### 1.6 その他

- **collection baseline**: `config/test_collection_baseline.json` = 9766、HEAD 実測 **9767**
  （+2 prompt_registry / −1 param 削除の内訳と整合）→ 更新要。
- **README 整合チェック**: ci.yml line 55-73 が `ruff=0 / mypy=<baseline> / format=0` の README 記載を要求。
  HEAD で `mypy=250`（JSON）vs README `mypy=500` → **False（赤）**。**base でも `mypy=366` vs `500` → False（赤）**。
  → pre-existing、かつ**ratchet が自動更新するたびに再発する構造的問題**（Phase D 報告）。
- **conftest コメント**: `tests/conftest.py:397` の実例 `storage_client / message_client / usage_client` は
  リポジトリに**存在しない**。部分一致で誤除外の危険を示した実例としては、正しくは
  `tests/unit/test_image_clients.py`（`test_age_client*` の実在は coverage/deep の 2 件）。
- **H-1**: `KNOWN_SHIMS` 3 件のうち `src.api.health` / `src.services.llm.circuit_breaker` は
  `git ls-files` で不存在（`src.infrastructure.config.settings` のみ存在）。

---

## Phase A: 即時修正（H 指摘）

### Step 1: H-1 — `KNOWN_SHIMS` の存在しない shim 2 件を削除

**対象**: `tests/regression/test_shim_imports.py` line 17- （`KNOWN_SHIMS` リスト）

**変更**:
```python
# 修正前（3 件）
KNOWN_SHIMS = [
    ("src.api.health", ["router"]),                                    # ← 追跡外。削除
    ("src.services.llm.circuit_breaker", ["CircuitBreaker", "LLMCircuitBreaker"]),  # ← 追跡外。削除
    ("src.infrastructure.config.settings", ["settings", "Settings", "ROOT_DIR"]),    # ← 存在。維持
    ...
]
```
- `src/api/health.py`・`src/services/llm/circuit_breaker.py` は `git ls-files` で 0 件（Q3 shim 焼却済み）。
- `test_shim_list_not_empty` が残り 1 件でも green を維持することを確認する。

**根拠（実測）**: `git ls-files src/api/health.py src/services/llm/circuit_breaker.py` → 空。
base/HEAD とも `test_shim_importable[src.api.health-symbols0]` と
`[src.services.llm.circuit_breaker-symbols1]` は clean checkout で ImportError 失敗（pre-existing 赤の一部）。

**検証**:
```bash
.venv/bin/python -m pytest tests/regression/test_shim_imports.py -q --timeout=60
git ls-files src/infrastructure/config/settings.py   # 1 件残ること
```
**受け入れ基準**: `test_shim_imports` が green（parametrize 1 件 + list_not_empty = 2 テスト）。
clean checkout でも同様に green になる（`src.infrastructure.config.settings` は追跡対象）。

---

### Step 2: H-2 — `check_untracked_imports.py` に変数解決 AST を実装

**対象**: `scripts/check_untracked_imports.py`（docstring line 14-21 の「既知の制限」を含む）

**変更**:
1. 現行の「文字列リテラルのみ」走査に**追加**で以下を解決する:
   - **module-scope 代入**: `KNOWN_SHIMS = [(...), ...]` のような `Name = List/Tuple/Set/Dict リテラル` を
     モジュールスコープで収集し、`import_module(変数名)` の引数をそのリテラルへ展開する。
     タプル/リストの先頭要素（`(module_path, symbols)` 形式）は先頭文字列を対象とする。
   - **parametrize 経由**: `@pytest.mark.parametrize("a,b", LISTNAME)` を関数デコレータから抽出し、
     テスト関数内の `import_module(a)` の `a` → `LISTNAME` → リテラルへ解決する。
2. 解決先が `src.` で始まるものだけを存在チェック対象にする（`patch()` の属性パス等を混ぜない）。
3. docstring の「既知の制限」を更新: 変数経由は**解決済み**であることを明記し、残る制限
   （f-string 組み立て等）のみを記載する。

**根拠（実測・プロトタイプ実証済み）**: 上記 §1.3。解決 67 件 / 欠落 2 件（Step 1 で消える）/ 誤検出 0。
素朴な全文字列走査は 548 件誤検出のため**不採用**。

**検証**:
```bash
.venv/bin/python scripts/check_untracked_imports.py            # exit 0（Step 1 済みなら欠落 0）
.venv/bin/python scripts/check_untracked_imports.py --list     # 既知 allowlist のみ表示
# 感度確認: 一時的に KNOWN_SHIMS に存在しないパスを追加 → exit 1 になること
```
**受け入れ基準**: 通常実行で exit 0。ダミーの存在しない `src.does.not.exist` を
`import_module` に渡す一時ファイルを置いて**検出されること**を実演し、一時ファイルは破棄する。

---

## Phase B: 設計負債（M 指摘）

### Step 3: M-1a — `ci_lint_ratchet.py` の mypy 実行を 1 プロセス化

**対象**: `scripts/ci_lint_ratchet.py`（`run_mypy` line 81 / `run_invalid_ignore` line 106）

**変更**:
- `--tool mypy` の実行時に `mypy src` を**1 回だけ**走らせ、その出力から
  (a) エラー件数（`Found N errors`）と (b) `Invalid "type: ignore" comment` の件数を**両方**解析する。
- `--tool invalid-ignore` は `--tool mypy` と同一の出力を再利用する（内部的に無視 or mypy へ統合）。
- **前提の明文化**: `pyproject.toml` `[tool.mypy] ignore_missing_imports = true` がある限り
  `--ignore-missing-imports` は冗長。この前提が崩れた場合に件数が変わるリスクを
  スクリプト docstring にコメントで記載する（例: 「ignore_missing_imports=false に変更したら
  invalid-ignore の走査は別途必要」）。

**根拠（実測）**: §1.2 — 両コマンド出力同一（235 件 / invalid-ignore 0）、時間 8.1s + 7.7s の二重コスト。

**検証**:
```bash
.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy           # 235/250 → GOOD（baseline は触らない）
.venv/bin/python scripts/ci_lint_ratchet.py --tool invalid-ignore # 同じ結果を返すこと
git checkout -- config/ci_lint_baseline.json                      # ← 実行で baseline が自動更新されるため必ず戻す
.venv/bin/python -m pytest tests/regression/test_H1_lint_ratchet.py -q --timeout=60
```
**受け入れ基準**: ratchet 2 ツールとも green。**`config/ci_lint_baseline.json` が変更されていないこと**
（`git status --short` が Step 3 の対象ファイルのみ）。`test_H1_lint_ratchet` green。
**注意**: `ci_lint_ratchet.py` を実行すると baseline JSON が自動降下する。検証後は必ず
`git checkout -- config/ci_lint_baseline.json` で復旧する（Q4 で一度事故が発生済み）。

---

### Step 4: M-1b — ci.yml の mypy 二重実行ステップを統合

**対象**: `.github/workflows/ci.yml` line 38-39（mypy ratchet）/ line 44-45（invalid-ignore）

**変更**:
- `mypy ratchet (hard gate)` と `invalid ignore ratchet` の 2 ステップを
  `mypy ratchet (hard gate / invalid-ignore を同一出力から解析)` の **1 ステップ**に統合する。
- `test_H1_ci_workflow_contract.py` は `ci_lint_ratchet.py` が static-analysis ブロックに
  含まれることのみを要求（実測済み）。`--tool mypy` を残す限り**契約は維持される**。

**根拠（実測）**: `tests/security/test_H1_ci_workflow_contract.py` 全 2 テストの assert 対象は
`"ci_lint_ratchet.py" in block` および baseline の追跡のみ。`--tool all` への変更も契約には非抵触。

**検証**:
```bash
.venv/bin/python -m pytest tests/security/test_H1_ci_workflow_contract.py -q --timeout=60
grep -n "ci_lint_ratchet" .github/workflows/ci.yml   # 1 箇所に統合されていること
```
**受け入れ基準**: 契約テスト green。ci.yml の static-analysis ジョブに ratchet が hard gate として残る。

---

### Step 5: M-2 — `src/services/prompt_registry.py` の整理（判断提示）

**対象**: `src/services/prompt_registry.py` + `tests/unit/test_prompt_registry.py`

**実測事実**（§1.5）:
1. 本番 importer 0 件（このファイルを使うコードが存在しない）。
2. 依存先 `PromptManager.get_template` が**不存在**（動作していない）。
3. `invalidate()` 呼び出し元 0 件。
4. テスト 4 件は全て MagicMock で実ロジックを検証していない。
5. mypy attr-defined エラー 2 件（`prompt_registry.py:33,37`）が **base でも存在（pre-existing）**。

**判断の提示（ユーザー選択）**:

| 選択肢 | 内容 | 影響 |
|---|---|---|
| **A（推奨）**: 削除** | `prompt_registry.py` と `test_prompt_registry.py`（4 件）を削除 | collection 9767 → **9763**。mypy 235 → **233**（pre-existing エラー 2 件消滅）。本番影響 0 |
| B: 実装修復 | `get_template` を `PromptManager` に実装し、実ロジックでテスト差し替え | 工数大。本番 importer 0 のため投資対効果 低い |

**このステップは承認後に着手する**。承認済みなら A で実装し、collection baseline の値を
Step 6 と**整合させる**（A 採用時は 9763、不採用なら 9767）。

**検証**（A の場合）:
```bash
.venv/bin/python -m pytest tests/unit -q --timeout=120 -p no:randomly
.venv/bin/python -m mypy src            # 233 件
.venv/bin/python scripts/check_untracked_imports.py
```
**受け入れ基準**: unit 全 green、mypy 件数が減ること、`grep -rn "services.prompt_registry" src tests` が空。

---

## Phase C: Low 指摘の解消

### Step 6: collection baseline の更新（9766 → 実測値）

**対象**: `config/test_collection_baseline.json`

**変更**: `{"collected": 9766}` → Step 5 の採否により **9767（B/未修正時）または 9763（A 採用時）**。
```bash
.venv/bin/python scripts/check_test_collection.py --update
git diff config/test_collection_baseline.json    # 値が実測と一致すること
```
**根拠**: HEAD ローカル collect-only 実測 **9767**（`main_collect_full.txt`、0 errors）。
内訳: 9766 + 2（prompt_registry テスト追加）− 1（param 削除）= 9767 と整合。

**検証**:
```bash
.venv/bin/python scripts/check_test_collection.py   # exit 0
```
**受け入れ基準**: exit 0。**clean checkout での成否は Phase D の pre-existing 問題**であり、
このステップの受け入れ基準には含めない。

---

### Step 7: conftest コメントの実例修正

**対象**: `tests/conftest.py` line 396-398（コメントのみ、ロジック変更なし）

**変更**:
```python
# 修正前
# 部分一致 "age_client" は storage_client / message_client / usage_client 等を
# 無警告で収集対象外にする過去インシデントの反省に従い、ファイル名限定とする
# 修正後（実在ファイルに差し替え）
# 部分一致 "age_client" は test_image_clients.py 等の他クライアントテストを
# 無警告で収集対象外にする過去インシデントの反省に従い、ファイル名限定とする
```
**根拠（実測）**: `storage_client` / `message_client` / `usage_client` を含むファイルは
`tests/conftest.py`（当該コメント自身）のみ。実在するクライアント系テストは
`tests/unit/test_image_clients.py`。`test_age_client*` の実在は coverage/deep の 2 件。

**検証**: `git diff tests/conftest.py` がコメント行のみであること。
**受け入れ基準**: `.venv/bin/python -m pytest tests/unit -q --timeout=120 -p no:randomly` が green
（収集ロジック不変のため件数が変わらないこと）。

---

### Step 8: semantic_cache L1 キー一致の回帰テスト追加

**対象**: 新規 `tests/unit/integrations/test_semantic_cache_l1_key.py`（既存テストファイルの追記でも可）

**背景（実測）**: `SemanticCacheManager._get_l1_key(prompt, task_type, genre, temperature)` を
`search`（line 174）と `prefetch_next`（line 426）が**同一関数・同一引数順**で呼んでいることは確認済み。
残る不確実性は、**呼び出し元 `src/services/redis_cache.py`（line 479 / 750）が
`self.semantic.search(prompt=..., task_type=..., genre=..., temperature=...)` と
シグネチャに一致したキーワード引数で呼んでいるか**の文字列一致のみ。

**変更**: redis_cache の L3 呼び出し引数と `SemanticCacheCache.search` のシグネチャを
**ソース AST で突き合わせる**回帰テストを追加する（実行時の import に依存しない静的検証）。
```python
def test_redis_cache_l3_call_matches_semantic_search_signature():
    """redis_cache の semantic.search 呼び出しが search のキーワード引数と一致すること。"""
    # redis_cache.py から self.semantic.search(...) のキーワード引数名を AST 抽出
    # semantic_cache.py の async def search の引数名と突き合わせ
    # 不一致（例: search(prompt=..., task_type=...) が temperature 欠落）で fail
```
**根拠（実測）**: `semantic_cache.py` line 174/270/426 が `_get_l1_key(prompt, task_type, genre, temperature)`
で統一、`redis_cache.py` line 479/750 が `prompt= / task_type= / genre= / temperature= / threshold=` で呼び出し。

**検証**:
```bash
.venv/bin/python -m pytest tests/unit/integrations/test_semantic_cache_l1_key.py -q --timeout=60
# 感度確認: redis_cache.py の呼び出しから temperature を一時的に外し、テストが赤くなること（後戻し）
```
**受け入れ基準**: テスト green。感度確認で redis_cache 側の不一致を検出できることを実演。

---

### Step 9: 不要 type-ignore 4 件の撤去 / narrowing 実修正

**対象**: §1.4 の 3 ファイル

**変更**:
1. **`src/services/proposal_isolation.py`**
   - line 94 の `# type: ignore[index,assignment]` は **unused → 撤去**。
   - line 96 の実エラー `[index]`（`Unsupported target for indexed assignment`）は
     ignore で塞がず、**P1 に従い narrowing で実修正**する:
     ```python
     if isinstance(res, dict):
         res["_sandbox_id"] = contexts[pid].session_id
         outputs[pid] = res
     else:
         # 例外がそのまま混入するケースを明示（現状 res は Exception 分岐済み）
         ...
     ```
     narrowing 後に line 97 の `# type: ignore[assignment]` が不要になれば**あわせて撤去**する。
2. **`src/audit/judge_panel.py`** line 392 / 395 の `# type: ignore[assignment]` は
   **通常モードでエラーが出ない（不要）→ 撤去**（base で line 394 にあった arg-type は
   lambda 化により消滅済みで、ignore は残骸）。
3. **`src/engine/nlp/japanese_tokenizer.py`** line 146 の `# type: ignore[arg-type]` は
   **不要 → 撤去**（assert narrowing により attr-defined が消滅済み）。

**根拠（実測）**: §1.4 の表。通常モード `mypy src --ignore-missing-imports` で該当行のエラーを実測。

**検証**:
```bash
.venv/bin/python -m mypy src                       # 235 以下（narrowing で減る可能性あり）
.venv/bin/python -m mypy src 2>&1 | grep -c 'Invalid "type: ignore"'   # 0
ruff check src && ruff format --check src          # 0 / 0
.venv/bin/python -m pytest tests/unit/test_proposal_isolation.py -q --timeout=60
```
**受け入れ基準**: mypy 件数 **235 以下**（narrowing 成功時は 234 以下）、invalid-ignore 0、
ruff 0 / format 0、`test_proposal_isolation` green。

---

### Step 10: README ベースライン値の整合（暫定修正）

**対象**: `README.md` line 24

**変更**:
```markdown
# 修正前
> 現在のベースライン値：`ruff=0` / `mypy=500` / `format=0`（`config/ci_lint_baseline.json`、policy: burn-down）。
# 修正後（config/ci_lint_baseline.json の実値と一致させる）
> 現在のベースライン値：`ruff=0` / `mypy=450` / `format=0`（`config/ci_lint_baseline.json`、policy: burn-down）。
```
（Step 5-A で mypy baseline が 233 等に動いたら、その**確定後の値**を書き込む）

**根拠（実測）**: ci.yml line 55-73 のチェックは
`f"ruff={ruff_errors} / mypy={mypy_errors} / format={format_files}" in README` を要求。
HEAD で expected `mypy=450` vs README `mypy=450` → **True（緑）**。**Step 2 (Q6) で README チェックを ratchet より前へ移動し、構造的乖離を解消。**

**検証**:
```bash
.venv/bin/python3 -c "
import json
b = json.load(open('config/ci_lint_baseline.json'))
exp = f'ruff={b[\"ruff_errors\"]} / mypy={b[\"mypy_errors\"]} / format={b[\"format_files\"]}'
assert exp in open('README.md').read(), exp
print('README OK:', exp)"
```
**受け入れ基準**: 上記スニペットが `README OK` を出す。
**限界の明記**: 本修正は**一度きりの整合**であり、次に `ci_lint_ratchet.py` が baseline を
自動更新すると**再び乖離する**。構造的解決は Phase D-2 で提示する。

---

## Phase D: pre-existing の報告（実修正せず、提案付きでユーザー判断）

> 以下 4 項目は**base `68137ce5` でも同一に再現することを実測で確認済み**であり、
> 本差分（4 コミット）の責任ではない。修正するかどうかはユーザーの判断を仰ぐ。

### D-1: clean checkout の `settings.toml` 欠如 → CI collection ゲートが構造的に赤（**解決済み Q6 Step3**）

- **実測**: HEAD clean = 9331 / 86 errors、base clean = 9324 / 86 errors、**エラーファイル集合完全一致**。
  全件 `FileNotFoundError: config/settings.toml`。
- **原因**: `config/settings.toml` は `.gitignore:13`。`GlobalConfigModel.load()` →
  `validate_all(strict=True)` が存在しないファイルで例外を送出。
- **修正（Q6 Step3 採用案 D1-a）**: `tests/conftest.py` の `pytest_configure` で
  `config/settings.toml` 欠如時に `config/settings.toml.example` からフォールバックを生成。
  `config/settings.toml.example` を新規追設。
- **実測結果**: clean worktree で `check_test_collection.py` rc=0、collected=9763（HEAD ローカルと同等）。
  base 由来の 86 errors / 436 件のテスト欠落が回復。

### D-2: README 手書き値と ratchet 自動更新の構造的乖離

- **実測**: HEAD `mypy=450`（JSON、warn_unused_ignores 有効化後）vs README `450` → チェック緑（Step 2 Q6 で解決済み）。
  ratchet が実行のたびに JSON を自動更新する一方、Step 2 (Q6) で以下を実施し構造的乖離を解消:
  1. README チェックステップを ratchet 4 ステップより前へ移動（JSON 書き換え前に照合）
  2. 減少時の自動 baseline 保存を廃止（`--update` で明示的に下げる）
  3. `--update` 時に README の該当行も書き換える（`_sync_readme_baseline`）
- **修正提案**: 上記により構造的乖離は解消。本計画（Q6）完了済み。

### D-3: regression ジョブの pre-existing 失敗（実態更新）

- **実測（フルスイート）**: base `68137ce5` で **23 failed / 9292 passed**、HEAD で **19 failed / 9301 passed**。
  HEAD の失敗 19 件はすべて base でも失敗（＝**本差分の回帰は 0 件**）。
- **本差分で解消済み 4 件**:
  `test_H1_lint_ratchet`（baseline understated → 実測値修正）/ `test_old_llm_shim_paths_removed` /
  `test_shim_imports` [`src.api.health`, `src.services.llm.circuit_breaker` の 2 parametrize]。
- **残存 pre-existing 19 件**:
  - Q5 D-3 記載 7 件: `test_H1_no_orphan_shims` ×2 / `test_shim_usage_stats` /
    `test_t6_plan_completion` / `test_tenant_fk_integrity` (alembic head) /
    `test_long_form_fact_retention` ×2
  - **D-3 未記載 12 件**: `test_real_easy_mode_api` / `test_production_e2e` /
    `test_spine_end_to_end` ×4 / `test_v5_workflow_e2e` / `test_v6_llm_call_budget` /
    `test_fusion_perf` / `test_easy_mode_export_with_data_ownership` ×2 /
    `test_get_db_manager_singleton`
  （うち `test_v6_llm_call_budget` と `test_get_db_manager_singleton` はフルスイート時のみ失敗、
  単体実行では green。順序依存の可能性あり）
- **注意**: `KNOWN_ORPHANS` 46 件のうち 45 件が削除済み shim 残骸で
  `test_known_orphans_still_exist` が赤。これは別途 `PLAN_R3_SHIM_REMOVAL_18STEPS.md` の管轄。
- **修正提案**: 残存 19 件は別計画（`PLAN_Q7_PREEXISTING_TEST_FAILURES_*.md`）に切り出し。

### D-4: clean checkout の `src.schemas` リーク（CI 再現性の限界）

- **実測**: clean clone には `src/schemas` が存在しない（`git ls-files src/schemas` = 0 件）にも
  関かわらず、`test_schemas_unification_complete`（26 件）が clean でも収集される。
  原因は元リポジトリへの **path hook リーク**（`__editable__` finder の除去を
  sitecustomize で行ったが、別経路が残存）。
- **意味**: 実 CI（GitHub Actions）では `ModuleNotFoundError` となり得る＝
  **clean 再現は保守的近似であり、CI と 1 件程度の差が残り得る**ことを明記する。
- **修正提案**: CI 側の実測（`gh` CLI 環境の整備後）で collection 件数を確認し、
  リーク経路（editable ファインダの特定）を除去する。

---

## 5. 最終ゲート（全 10 ステップ完了時）

```bash
ruff check src tests config scripts          # 0
ruff format --check src                      # 0
.venv/bin/python -m mypy src                 # ≤ 235（Step 5-A, Step 9 で減少）
.venv/bin/python -m pytest tests/unit -q --timeout=120 -p no:randomly   # 7765 以上 green
.venv/bin/python scripts/check_test_collection.py --update && .venv/bin/python scripts/check_test_collection.py  # exit 0
.venv/bin/python scripts/check_untracked_imports.py                     # exit 0
.venv/bin/python -m pytest tests/security/test_H1_ci_workflow_contract.py tests/regression/test_shim_imports.py -q  # green
git status --short   # config/ci_lint_baseline.json が意図せず更新されていないこと
```

**受け入れ基準**:
1. 上記全コマンドが green（mypy は 235 以下、件数は 0 にしない）。
2. 各ステップが 1 コミットで分離され、コミットメッセージに実測根拠が書かれている。
3. Phase D の 4 項目について、**報告文（D-1〜D-4）がユーザーに提示され、判断が記録される**。

---

## 6. リスク

| リスク | 影響 | 緩和 |
|---|---|---|
| `ci_lint_ratchet.py` 実行で baseline JSON が自動更新される | 意図しない baseline 降下が diff に混入（Q4 で発生済み） | 各検証後に `git checkout -- config/ci_lint_baseline.json` を必ず実行 |
| Step 2 の AST 解決が過剰に解決し誤検出 | ゲートが誤って赤になる | プロトタイプ実測（誤検出 0）を維持。全文字列素朴走査（548 件誤検出）は不採用と明記 |
| Step 5-A（削除）の採否で Step 6 の値が変わる | baseline と collection の不整合 | Step 5 の承認を Step 6 の**前**に取得する |
| Step 9 の narrowing が想定外の mypy エラーを増やす | mypy 件数が 235 超になる | narrowing 失敗時は「ignore 位置の正しい移設」にフォールバック（94→96 へ `[index]`） |
| clean 再現の path hook リーク（D-4） | clean 実測が CI より楽観的になり得る | D-4 として明記し、CI 実測で最終確認（gh 環境整備後に別計画） |
| Phase D を無視して先へ進む | CI が**構造的に赤**（collection / README / regression）のままマージされる | 本計画は Phase D の**報告**を必須とする（実修正はユーザー判断） |
