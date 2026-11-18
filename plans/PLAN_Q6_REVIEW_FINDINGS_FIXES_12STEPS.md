# PLAN_Q6: 差分レビュー残指摘の是正 — CI 必赤 3 件の回復と型ゲートの実体化 (12 STEPS)

> **目的**: `fix/q1-red-gate-recovery`（`68137ce5..820308f2`、16 コミット / 110 ファイル）に対する
> コードレビューで検出した指摘を是正する。**レビューは全指摘について実測で再現・帰属を完了済み**であり、
> 各ステップは推測ではなく実測値を根拠に実装する。
>
> **本計画の特徴**:
> 1. **CI が構造的に赤になる経路 3 件（P0）を Step 1〜3 で先に潰す**。これが無いと以降の検証結果が CI で見えない。
> 2. **型ゲート（`invalid-ignore`）が実質無効であることを是正する（P1）**。真の問題は「未使用 ignore 216 件」。
> 3. pre-existing（本差分に起因しない赤）は**修正せず証拠付きで報告**し、ユーザー判断を仰ぐ（Phase 0 / スコープ外）。
>
> **対象ブランチ**: `fix/q1-red-gate-recovery`（HEAD `820308f2`、ワークツリークリーン）
> **前提**: `PLAN_Q4_REVIEW_REMEDIATION_24STEPS.md` / `PLAN_Q5_DIFF_REVIEW_FIXES_10STEPS.md` 完了済み。
> **作業方針**: 1 ステップ = 1 コミット。各 Phase は自分の検証コマンド green まで次へ進まない（Q5 P5 継承）。
> **スコープ外**: 「スコープ外・別計画へ」章を参照。
>
> **実測根拠（本計画で全項目を再現済み）**:
> - ruff 赤: `scripts/ci_lint_ratchet.py --tool ruff` → `actual=1 baseline=0` / rc=1
> - README 赤: ratchet 実行後に ci.yml line 49-65 のスニペットを実行 → `rc=1`（期待値 `mypy=234`）
> - collection 赤: clean worktree `820308f2` で `check_test_collection.py` → `actual=9331 baseline=9761` / rc=1
> - unused ignore: `mypy src --warn-unused-ignores` → `Found 450 errors in 153 files`、`[unused-ignore]` **216 件**
> - 通常 mypy: `mypy src` → `Found 234 errors in 113 files`（baseline 250）
> - テスト帰属: base `68137ce5` フルスイート **23 failed / 9292 passed**、HEAD **19 failed / 9301 passed**

---

## 0. 実測サマリー（全根拠）

### 0.1 CI が赤になる 3 経路（すべて再現済み）

| # | 該当ステップ | 経路 | 再現結果 |
|---|---|---|---|
| P0-1 | lint job 最初のステップ | `tests/unit/integrations/test_semantic_cache_l1_key.py:21` の未使用 `import pytest`（F401） | `ci_lint_ratchet.py --tool ruff` → `actual=1 baseline=0` **rc=1** |
| P0-2 | lint job「README 静的解析ベースライン整合性チェック」 | `ci_lint_ratchet.py --tool mypy`（`--update` 無し）でも actual < baseline なら `_save_baseline()` で `config/ci_lint_baseline.json` を書き換える（**250 → 234 実測**）。後段の README チェックは **JSON を再読込**して `ruff=0 / mypy=250 / format=0` を照合 | 期待値 `ruff=0 / mypy=234 / format=0` が README に無く **rc=1** |
| P0-3 | test job「Test collection regression guard」 | `config/settings.toml` が `.gitignore:13` 対象。clean 環境で 86 ファイルが collection エラー → 436 テスト欠落（Q5 D-1） | clean worktree で **`actual=9331 baseline=9761` / rc=1**（430 件減少） |

> P0-1 が最初のステップなので、**修正しない限り以降の CI は一切実行されない**。
> P0-2 は P0-1 を直しても発火する（mypy ratchet が README チェックより先に JSON を書くため）。
> P0-3 は test ジョブであり、lint job とは独立に毎回赤。

### 0.2 型ゲートの実測（P1 の根拠）

| コマンド | 結果 | 意味 |
|---|---|---|
| `mypy src` | `Found 234 errors in 113 files` | 現行 `mypy_errors` の実体 |
| `mypy src --warn-unused-ignores` | `Found 450 errors in 153 files`、うち `[unused-ignore]` **216 件** | 未使用 ignore の実数（450 − 234 = 216） |
| `# type: ignore foo`（構文不正）を単体ファイルで実行 | `error: Invalid "type: ignore" comment [syntax]` / `Found 1 error` | **`Invalid "type: ignore" comment` は通常実行でも error に計上される** |
| `scripts/ci_lint_ratchet.py --tool mypy` | `invalid_ignore_errors: 0` | つまり `invalid_ignore_errors` は `mypy_errors` の**部分集合**で独立検出力ゼロ |

- 結論: 新設した `invalid-ignore` メトリクスは「mypy の構文不正コメント」しか見ず、それ自体が既に
  `mypy_errors` に含まれる。**「不要・無効な ignore」は `--warn-unused-ignores` でしか見えない**。
- 本差分で**新規追加された未使用 ignore（6 件）**（`--warn-unused-ignores` で特定、いずれも ignore 除去で 234 は不変）:

| ファイル:行 | 内容 |
|---|---|
| `src/publishing/exporters/base.py:628` | `cls = _EXPORTERS.get(...)  # type: ignore[abstract]`（代入行に error code が当たらない） |
| `src/rules/state_machine.py:174` | `items()` 内の**コメントのみの行** `# type: ignore[arg-type]`（該当行にエラーなし＝完全ノーオペ） |
| `src/llm/unified/adapters/gemini.py:59` | `async def astream(...)  # type: ignore`（bare） |
| `src/llm/unified/adapters/openai.py:53` | 同上 |
| `src/models/narrative_metrics_db.py:14` | `_LocalBase = declarative_base()  # type: ignore[misc]` |
| `src/models/plot.py:910` | `)  # type: ignore[call-arg]` |

### 0.3 テスト帰属（回帰ゼロの証明）

| | failed | passed |
|---|---|---|
| base `68137ce5` | **23** | 9292 |
| HEAD `820308f2` | **19** | 9301 |

- HEAD の失敗 19 件は**すべて base でも失敗（pre-existing）＝本差分の回帰は 0 件**。
- うち 4 件は**本差分で解消済み**: `test_H1_lint_ratchet` / `test_old_llm_shim_paths_removed` /
  `test_shim_imports`（`src.api.health`, `src.services.llm.circuit_breaker`）。
- 残る 19 件の内訳: **Q5 D-3 記載 7 件**（orphan shims×2 / shim_usage_stats / t6_plan / alembic head / long_form×2）+
  **D-3 未記載 12 件**（`test_real_easy_mode_api` / `test_production_e2e` / `test_spine_end_to_end`×4 /
  `test_v5_workflow_e2e` / `v6_llm_call_budget` / `fusion_perf` / `test_easy_mode_export`×2 / `test_get_db_manager_singleton`）。
- ※ base/HEAD とも「フルスイートでのみ失敗」の順序依存 2 件（`v6_llm_call_budget`, `test_get_db_manager_singleton`）
  は単体実行では green。D-3 の把握（9 項目）と実態が乖離しているため計画書側の記録更新を Step 10 で行う。

### 0.4 検証済みで問題なしと判断した項目（是正不要・検証のみ）

- `src/llm/clients/` / `src/services/prompt_registry.py` 削除後の残参照ゼロ、`KNOWN_SHIMS` 削除の正当性
- `src/models/__init__.py` 遅延化（循環 import 解消の説明と実装一致、後方互換シンボル維持）、`PlotDbModel` 移設の完全一致
- `tests/conftest.py` の `age_client` 部分一致バグ修正（`tests/unit/test_image_clients.py` が黙殺されていた → 復帰）
- `src/plugins/audio/voicevox.py` の `import urllib.parse` 追加（潜在 NameError の実修正）
- `IUnifiedLLMClient.astream` の `async def` → `def` 変更（呼び出し側 **0 件**、挙動リスクなし）
- 新規/変更テストは green（`test_uow_commit` / `test_editorial_assistant_service` / `test_semantic_cache_l1_key` /
  `test_H1_lint_ratchet` / `test_shim_imports`）、`test_H1_ci_workflow_contract` 8 passed
- ゲート実測: format 0 / `check_untracked_imports` exit 0 / `check_layer_boundaries` exit 0

---

## 1. Phase 0: 判断待ち事項（着手前に確定させる）

| ID | 論点 | 選択肢 | 推奨 | 判断者 |
|---|---|---|---|---|
| **D1** | P0-3（clean checkout の collection 赤 / Q5 D-1 と同じ論点） | **(a)** `tests/conftest.py` の `pytest_configure`（collection 前）で `config/settings.toml` 欠如時に最小フォールバックを生成し、`config/settings.toml.example`（新規追設）と整合させる<br>**(b)** ci.yml の test ジョブに生成ステップを追加（ローカル clean 再現は不可のまま）<br>**(c)** baseline を clean 実測 9331 に合わせる（436 件欠落を黙認＝ゲートの意味が薄まる）<br>**(d)** `check_test_collection.py` ステップを ci.yml から一旦撤回（D-1 解決まで延期） | **(a)** | ユーザー |
| **D2** | P0-2（ratchet の自動書き込みと README チェックの構造的乖離 / Q5 D-2 と同じ論点） | **(a)** README チェックステップを ratchet 4 ステップの**前**へ移動（最小変更）<br>**(b)** 「実測減少時」の `_save_baseline()` を**ログのみ**に変更（追跡ファイルを書き換えない）<br>**(c)** `--update` 実行時に README の該当行も書き換える（D-2(a)） | **(a)+(b)+(c) 併用**（(a) で CI が赤くならない、(b) でローカル実行が tree を汚さない、(c) で手動更新時の乖離を構造的に防ぐ） | ユーザー |
| **D3** | P1（`invalid-ignore` の実体化方式） | **(A)** `pyproject.toml [tool.mypy]` に `warn_unused_ignores = true` を**常時化**し、1 プロセス維持のまま `mypy_errors` を 450 ベースに切り替え＋`unused_ignore_errors`（216）を二重管理。`invalid_ignore_errors` は**削除**（`mypy_errors` に内包のため）<br>**(B)** 現行 `mypy_errors`（234）を維持し、`--warn-unused-ignores` を**別プロセス**（+約 8 秒）で走らせて `unused_ignore_errors` だけ取る。`invalid_ignore_errors` は削除 | **(A)**（M-1a の 1 プロセス化を保て、README/baseline 連動更新は Step 2 の (c) で吸収できる） | ユーザー |
| **D4** | `SemanticCacheManager.prefetch_next`（既定 OFF・docstring 自認で「ヒット率向上ゼロ・API コストのみ」） | **(a)** 現状維持（Step 9 で「既定 OFF」を明記するのみ）<br>**(b)** 削除を PLAN_Q4-R2 バックログへ接続 | **(a)**（本計画では Step 9 でドキュメント明記まで） | ユーザー |

> **D1〜D3 の判断が下るまで Step 3 / Step 4 には着手しない**（Step 1・2・5・6・7・8 は判断不要で即実施可能）。

---

## Phase A: P0 — CI 必赤の解消（Step 1〜3）

### Step 1: P0-1 — 新規テストの未使用 import を除去

**対象**: `tests/unit/integrations/test_semantic_cache_l1_key.py:21`

**変更**:
```python
# 修正前（line 20-21）
from pathlib import Path

import pytest        # ← 未使用（fixture / mark / raises のいずれも不使用）を削除
```
- `ruff --fix` でも可（`*.py` の F401 自動修復）。人手で削除する場合は import 節のみ。

**根拠（実測）**:
- `ruff check src tests config scripts --output-format=concise` → `tests/unit/integrations/test_semantic_cache_l1_key.py:21:8: F401 ... Found 1 error.`
- `scripts/ci_lint_ratchet.py --tool ruff` → `ruff: actual=1 baseline=0` / **rc=1**（CI lint job 最初のステップ）

**検証**:
```bash
.venv/bin/ruff check src tests config scripts        # Found 0 errors
.venv/bin/python scripts/ci_lint_ratchet.py --tool ruff     # rc=0
.venv/bin/python -m pytest tests/unit/integrations/test_semantic_cache_l1_key.py -q --timeout=60   # 2 passed
```
**受け入れ基準**: ruff ratchet が `actual=0 baseline=0` で rc=0。当該テスト 2 passed。
**コミット**: `fix(plan-q6 Step1 P0): test_semantic_cache_l1_key の未使用 import を除去 (ruff 1->0)`

---

### Step 2: P0-2 — ratchet の自動書き込みと README チェックの構造的乖離を解消（D2）

**対象**: `.github/workflows/ci.yml:36-65`（lint job のステップ順）、`scripts/ci_lint_ratchet.py`、`README.md:24`

**変更**（D2 採用案に応じた 3 点。推奨は併用）:

**(a) ステップ順の変更（最小・必須）**: `README 静的解析ベースライン整合性チェック` を
**すべての ratchet ステップより前**（`Setup Python` 直後、現 line 36 の手前）へ移動する。
理由: ratchet は実行のたびに JSON を書くため、**JSON が checkout 直後の状態で照合する順序を保証する**必要がある。

```yaml
      - name: README 静的解析ベースライン整合性チェック   # ← ここへ移動（ratchet より前）
        working-directory: .
        run: |
          python3 -c "..."   # 既存スクリプトは無変更
      - name: ruff ratchet (hard gate)
        run: python scripts/ci_lint_ratchet.py --tool ruff
      - name: mypy ratchet (hard gate / ...)
        run: python scripts/ci_lint_ratchet.py --tool mypy
      ...
```

**(b) 実測減少時の `_save_baseline()` を廃止（ログのみ）**: `scripts/ci_lint_ratchet.py` の
`_check_single_metric()` 内 `if actual < base:` 分岐を `data[key] = actual`（dirty = True）から
**dirty = False のままログ出力のみ**へ変更する。
- 根拠: 現行は非 `--update` 実行でも追跡ファイルを書き換え、ローカルの `git status` を汚す
  （Q5 の最終ゲートが「意図しない baseline 更新がないこと」を要求していることと矛盾）。
- 意味変化: baseline（上限床）が自動では下がらず、床の引き下げは `--update` の明示操作のみ。
  上限管理（actual > base で失敗）としてのラチェット性は維持される。
- 副作用: baseline が実測より緩いまま残る（現在 250 vs 234）。**README 表記（250）と一致するため
  README チェックは安定して green**。床を下げるときは (c) を使う。

**(c) `--update` が README の該当行も書き換える（D-2(a)）**: `_save_baseline()` と同じく
`--update` 時に README を正規表現置換するヘルパー `sync_readme_baseline(data)` を追加する。
```python
# README.md に当該パターンは 1 箇所のみ（grep -c 実測 = 1）
PAT = re.compile(r"ruff=\d+ / mypy=\d+ / format=\d+")
PAT.sub(f'ruff={data["ruff_errors"]} / mypy={data["mypy_errors"]} / format={data["format_files"]}', text)
```

**根拠（実測・再現済み）**:
- `.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy` → `mypy: actual=234 baseline=250` /
  `GOOD: 16 件減少。ベースラインを下げた。` → `config/ci_lint_baseline.json` が `250 → 234` に変化
- その後 ci.yml line 49-65 のスニペットを実行 → `README check -> FAIL` / 期待値 `ruff=0 / mypy=234 / format=0` / **rc=1**
- README の該当パターンは 1 箇所のみ: `README.md:24`

**検証**（ci.yml の順序をローカルで再現する）:
```bash
.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy    # rc=0（(b) 適用後）
.venv/bin/python scripts/ci_lint_ratchet.py --tool ruff    # rc=0
.venv/bin/python - <<'PY'                                   # README チェック再現 → rc=0
import json; b=json.load(open('config/ci_lint_baseline.json')); r=open('README.md').read()
exp=f'ruff={b["ruff_errors"]} / mypy={b["mypy_errors"]} / format={b["format_files"]}'
assert exp in r, exp
print('README check OK:', exp)
PY
git status --short    # 空（追跡ファイルが変化しない）
# --update 運用の確認:
.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy --update && grep -n "ruff=0 / mypy=" README.md
```
**受け入れ基準**: 上記 4 コマンドがすべて rc=0 かつ `git status --short` が空。
Step 1+2 完了時点で lint job の全ステップが通ることを、clean worktree でも確認する（Step 12 で一括）。
**コミット**: `fix(plan-q6 Step2 P0): README チェックを ratchet より前へ移動 + 減少時保存の廃止 + --update が README 連動 (D2 a/b/c)`

---

### Step 3: P0-3 — clean checkout の collection ゲートが毎回赤（D1）

**対象**: `tests/conftest.py`（`pytest_configure`）/ `config/settings.toml.example`（新規）/ `scripts/check_test_collection.py` / `config/test_collection_baseline.json`

**変更（推奨案 D1-(a)）**:
1. `config/settings.toml.example`（**現状リポジトリに存在しない**＝Q5 D-1 実測）を新規追設する。
   内容は `GlobalConfigModel` が `validate_all(strict=True)` を通過する**最小構成**のみ。
   ⚠️ `src/infrastructure/config/project_context.py:139` のコメントのとおり settings.toml は秘密情報
   （API キー等）を含み得る前提のため、**example には秘密を一切書かない**こと（空/ダミー値のみ）。
2. `tests/conftest.py` に `pytest_configure(config)` を追加し、`config/settings.toml` 欠如時のみ
   example をコピー（または最小 TOML を書き出す）。**collection の前**に走ることを確認する。
   - 参照入口: `src/infrastructure/config/validator.py:43 load_settings_toml()` /
     `src/infrastructure/config/project_context.py:133 settings_path = BASE_DIR / "config" / "settings.toml"` /
     `validator.py:182 _safe_load(...)`（既存フォールバックの有無を先に確認し、二重実装を避ける）
3. 収集件数を再実測して `config/test_collection_baseline.json` を確定（Step 9 と連動）。

**根拠（実測）**: clean worktree `820308f2` で
`check_test_collection.py` → `test collection: actual=9331 baseline=9761` / **430 件減少** / **rc=1**。
`ls config/settings.toml` → `No such file`（`.gitignore:13` に `config/settings.toml`）。

**検証**:
```bash
git worktree add -f /tmp/opencode/q6_clean HEAD
cd /tmp/opencode/q6_clean
/home/annahoikuen/autonovel/.venv/bin/python scripts/check_test_collection.py   # rc=0 を目指す
/home/annahoikuen/autonovel/.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider 2>&1 | tail -3
# エラーファイル 86 件が 0 になり、collected が HEAD ローカル（9763）と同等であること
cd - && git worktree remove --force /tmp/opencode/q6_clean
```
**受け入れ基準**: clean worktree で `check_test_collection.py` が **rc=0**、collection error **0 件**、
`config/test_collection_baseline.json` が clean 実測値以上（減少検知の感度を保つ）。
**代替**: D1-(b) 採用時は ci.yml の test ジョブに生成ステップを追加し、(c) 採用時は baseline を
clean 実測（9331）へ、(d) 採用時は `ci.yml:147-148` のステップを削除する。
**コミット**: `fix(plan-q6 Step3 P0): settings.toml 欠如時のフォールバック生成で clean checkout の collection ゲートを緑化 (D1-a)`

---

## Phase B: P1 — 型ゲートの実体化（Step 4〜5）

### Step 4: P1 — `invalid-ignore` メトリクスを「未使用 ignore」に置き換える（D3）

**対象**: `pyproject.toml`（`[tool.mypy]` line 237-）、`scripts/ci_lint_ratchet.py`、`config/ci_lint_baseline.json`、`README.md:24`、`tests/regression/test_H1_lint_ratchet.py`

**変更（推奨 D3-(A)）**:
1. `pyproject.toml [tool.mypy]` に `warn_unused_ignores = true` を追加する。
2. `scripts/ci_lint_ratchet.py`:
   - `INVALID_IGNORE_RE` を廃し、**`UNUSED_IGNORE_RE = re.compile(r"\[unused-ignore\]")`** を導入。
   - `_run_mypy_once()` の戻り値を `(mypy_errors, unused_ignore_errors)` へ変更（**1 プロセス維持**、
     `--warn-unused-ignores` は pyproject 既定化によりコマンド引数不要）。
   - `check_tool("mypy")` は `(mypy_errors, unused_ignore_errors)` の 2 メトリクスを検証。
   - `BASELINE_KEYS` / ドキュメント（対象説明）を更新し、`invalid_ignore_errors` を**削除**する
     （`Invalid "type: ignore" comment` は `[syntax]` として `mypy_errors` に内包される＝実測根拠 §0.2）。
3. `config/ci_lint_baseline.json`: `mypy_errors: 450`（warn 既定化後の実測）、
   `unused_ignore_errors: 216`、`invalid_ignore_errors` キー削除、`history` に追記
   （**「劣化ではなく管理対象の追加（同一コード状態で warn の有無だけの差）」と明記**すること）。
4. `README.md:24` を `ruff=0 / mypy=450 / format=0` へ更新（Step 2-(c) を併用できる）。
   README line 25 の陳腐化（`1122 → 952 / 目標 567`）は Step 10 で一括更新する。
5. `tests/regression/test_H1_lint_ratchet.py` の実測値注記（「mypy 実測 235」→実態へ）と
   「baseline を 200 に下げると失敗する」挙動を新メトリクスに合わせて再確認する。

**根拠（実測）**: §0.2 の表。特に「`Invalid "type: ignore" comment` は通常実行でも error に計上される」
（`# type: ignore foo` を単体実行 → `Found 1 error` / `[syntax]`）が `invalid_ignore_errors` 廃止の根拠。

**検証**:
```bash
.venv/bin/python -m mypy src                       # Found 450 errors（warn 既定化後）
.venv/bin/python -m mypy src | grep -c "\[unused-ignore\]"   # 216
.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy      # rc=0（mypy 450/450, unused 216/216）
# 感度: 任意のファイルに不要な `# type: ignore` を 1 件追加 → unused が 217 になり rc=1 になること
```
**受け入れ基準**: ratchet が新 2 メトリクスで green。**「不要 ignore を 1 件追加すると赤」が実演できる**。
**代替（D3-(B)）**: `mypy_errors` を 234 のまま維持し、`--warn-unused-ignores` の別プロセス
（+約 8 秒）で `unused_ignore_errors` のみ取得。この場合 `mypy_errors` baseline は 234 のまま。
**コミット**: `fix(plan-q6 Step4 P1): invalid-ignore を unused-ignore 実体化 (warn_unused_ignores 常時化, 1プロセス維持) + baseline/README 連動`

---

### Step 5: P1 — 本差分で新規追加された未使用 ignore 6 件を撤去

**対象**: §0.2 の表に挙げた 6 ファイル（本レビューで diff 経由の新規追加と特定済み）

**変更**（各ファイルで該当行の `# type: ignore...` を除去。mypy エラー数は**不変**であることが撤去可否の判定基準）:

| ファイル:行 | 除去対象 | 備考 |
|---|---|---|
| `src/publishing/exporters/base.py:628` | `cls = _EXPORTERS.get(...)  # type: ignore[abstract]` | line 629 `return cls()` の ignore は**必要**（残す） |
| `src/rules/state_machine.py:174` | コメントのみ行 `# type: ignore[arg-type]` | 行自体を削除。`__iter__`（line 170）の ignore は実必要（`mypy` Success 確認済）のため残す |
| `src/llm/unified/adapters/gemini.py:59` | bare `# type: ignore` | `astream` は呼び出し側 0 件、ABC 変更後も互換 |
| `src/llm/unified/adapters/openai.py:53` | bare `# type: ignore` | 同上 |
| `src/models/narrative_metrics_db.py:14` | `# type: ignore[misc]` | line 15-16 の `# type: ignore[valid-type, misc]` は**必要**（残す） |
| `src/models/plot.py:910` | `# type: ignore[call-arg]` | 除去後も `mypy src` が 450 のままであることを確認 |

**根拠（実測）**: `mypy src --warn-unused-ignores` の出力に当該 6 行が `Unused "type: ignore" comment` として現れる。
**検証**:
```bash
.venv/bin/python -m mypy src                       # 総数 450 -> 444（unused 6 件分のみ減少）
.venv/bin/python -m mypy src | grep -c "\[unused-ignore\]"   # 216 -> 210
.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy      # rc=0（baseline が 450/216 のため actual < base）
.venv/bin/python scripts/ci_lint_ratchet.py --tool ruff      # rc=0
.venv/bin/ruff format --check src                             # 0 files would be reformatted
```
**受け入れ基準**: unused が **216 → 210**、mypy 総数が **450 → 444**、ruff / format ratchet green。
> 残る 210 件は本差分外の pre-existing。バーンダウン計画へ接続（Step 12 の報告に含める）。
**コミット**: `fix(plan-q6 Step5 P1): 本差分で混入した unused type-ignore 6 件を撤去 (216->210)`

---

## Phase C: P2 — 挙動・契約の是正（Step 6〜9）

### Step 6: P2 — `NarouExporter.export_stream` の `len(Iterable)` 実行時欠陥を解消

**対象**: `src/publishing/exporters/base.py:439-462`

**変更**:
```python
def export_stream(self, novel: Dict[str, Any], chapters: Iterable[Dict[str, Any]]) -> Generator[str, None, None]:
    chapters = list(chapters)          # ← 実体化。len() を安全にし、ジェネレータ渡しでも動く
    header = self._header(novel)
    ...
    if i < len(chapters) - 1:          # ← `# type: ignore[arg-type]` を除去
        yield "\n=====\n"
```
- 理由: シグネチャは `Iterable` だが `len()` を呼ぶ＝**型エラーを ignore で隠した結果、実行時 `TypeError` が残っている**。
  兄妹実装（`_render_markdown_stream` line 346 ほか）は `enumerate` のみで `len` 不使用。
- 冒頭で 1 度だけ `list()` 化すれば、他 exporter と挙動が揃い、ストリームの 1 回走査制約も守られる。

**根拠（実測）**: `mypy src --warn-unused-ignores` で ignore は "used"（＝line 462 に実エラーあり）。
`export_stream` の呼び出しは現状 `export()`（`List`）と tests のみで、`src/backend|src/services` からの
ジェネレータ渡しは 0 件（＝**現時点では未発火の潜在欠陥**）。

**検証**:
```bash
.venv/bin/python -m mypy src/publishing/exporters/base.py     # ignore 除去後もエラー増なし
.venv/bin/python -m pytest tests/unit/test_exporters_full.py \
  tests/unit/publishing/exporters -q --timeout=120            # green
```
**追加テスト**（`tests/unit/publishing/exporters/exporters/test_base.py` に 1 件）:
`NarouExporter().export_stream(NOVEL, (c for c in CHAPTERS))`（**ジェネレータ渡し**）が
例外なく `=====` 区切りを含むことを検証する。
**受け入れ基準**: ジェネレータ渡しテスト green、`type: ignore[arg-type]` が当該行から消える。
**コミット**: `fix(plan-q6 Step6 P2): NarouExporter の len(Iterable) を list 化して ignore で隠していた実行時欠陥を解消`

---

### Step 7: P2 — `UnitOfWork.commit()` の冪等化（二重 outbox flush の予防）

**対象**: `src/backend/database/uow.py:64-77`、`tests/unit/database/test_uow_commit.py`

**変更**:
```python
async def commit(self) -> None:
    """UnitOfWork のコミット（トランザクション境界）。"""
    async def _commit_with_retry():
        ...
    await retry_on_lock()(_commit_with_retry)()
    logger.info(f"[UOW] ... Staged {len(self._chroma_additions)} Chroma adds, ...")
    # コミット済みステージをクリアし、__aexit__ による二重 flush を防ぐ（冪等化）
    self._chroma_additions.clear()
    self._chroma_deletions.clear()
```
- 既存の `__aexit__` の `finally` でもクリアされるため、クリアは冪等（二重クリアは無害）。
- ログは `clear()` より前に評価されるため出力は変わらない。

**根拠（実測）**:
- `ChromaOutboxService.flush`（`src/backend/database/outbox.py:14-29`）は `session.add` を毎回実行する**非冪等**。
- `_chroma_additions/_chroma_deletions` のクリアは `__aexit__` の `finally`（uow.py:235-236）のみ。
  → 「`async with` 内で明示 `commit()` → 正常終了で `__aexit__` が再 commit」すると**同一内容の outbox 行が 2 件**。
- ただし現状 `grep -rn "stage_chroma_add|stage_chroma_delete" src` → **0 件**（本番 staging なし）、
  backend `UnitOfWork` の明示 `commit()` 呼び出しも 0 件（`self.uow.commit()` は application 層の
  `IUnitOfWork` プロトロル経由のみ、`BookUseCases` は commit 呼びなし）＝ **現状 latent**。
- base `68137ce5` には `UnitOfWork.commit()` が**存在しなかった**（`git show` のメソッド一覧で確認）。

**追加テスト**（`tests/unit/database/test_uow_commit.py` に 1 件）:
```python
async def test_explicit_commit_then_aexit_does_not_duplicate_outbox():
    """async with 内の明示 commit 後も __aexit__ が例外なく完了し、outbox が 1 件のままであること。"""
    # stage_chroma_add -> await uow.commit() -> with 終了 -> outbox 行数 == 1 を検証
```
**検証**:
```bash
.venv/bin/python -m pytest tests/unit/database/test_uow.py tests/unit/database/test_uow_commit.py \
  tests/unit/database/test_uow_integration.py -q --timeout=120     # green
.venv/bin/python -m mypy src/backend/database/uow.py                # エラー増なし
```
**受け入れ基準**: 二重 commit テストを含む UOW 系 3 ファイル green、mypy/ruff green。
**コミット**: `fix(plan-q6 Step7 P2): UnitOfWork.commit を冪等化し __aexit__ による outbox 二重 flush を予防 + テスト追加`

---

### Step 8: P2 — `gacha_service` の到達不能コード整理

**対象**: `src/services/gacha_service.py:273-282`

**変更**: ループ後の fallback `return GachaPlan(...)`（11 行）は**到達不能**
（内側 `if attempt == max_retries: return ...` が必ず返すため）。
- **まず mypy の挙動を確認してから**、以下のいずれかで単一経路に整理する:
  1. ループ後のブロックを削除し、mypy が `Missing return statement` を出さない実装へ
     （例: 内側 fallback を `else` に移し、ループ後に `raise RuntimeError("unreachable")` を置く）
  2. 維持する場合はコメントで「到達不能（mypy の missing-return 対応）」と明記し、生成ロジックの
     重複をコメントアウトではなく**共通ヘルパー化**して二重メンテを防ぐ
- 併せて `except (ValidationError, json.JSONDecodeError, BaseException)` の
  **`BaseException` が `CancelledError`/`KeyboardInterrupt` を握りつぶしてフォールバック案を返す**点を
  （pre-existing として）`except Exception` へ寄せるかを判断する。推奨: `Exception` に変更 +
  `asyncio.CancelledError` は伝播させる。

**根拠（実測）**: `sed -n 230,300p` で内側 return の存在と後続ブロックの重複を確認。
**`src/services/gacha_service.py` の専用単体テストは存在しない**
（`grep -rln "gacha_service" tests` → 0 件。`test_v5_workflow_e2e` / `test_blind_gacha_flow` は e2e/integration、
`tests/unit/agents/test_planning_subversion.py::test_proposal_gacha_passes_kwargs` は別物の proposal gacha）。

**検証**:
```bash
.venv/bin/python -m mypy src/services/gacha_service.py    # エラー増なし（missing-return が再燃しないこと）
.venv/bin/ruff check src/services/gacha_service.py        # 0
.venv/bin/python -m pytest tests/unit -q --timeout=120 -m "not integration and not perf and not slow" \
  -p no:randomly                                          # failed が 19 件を超えない（回帰 0）
```
**追加テスト（必須に近い）**: LLM モックが常に `JSONDecodeError` を返す場合にフォールバック案が返ることを
検証する unit テストを `tests/unit/services/test_gacha_service.py`（新規）に 1 件追加
（現状この経路はテストされていない）。
**受け入れ基準**: mypy/ruff green、到達不能ブロックが消えまたは意図が明記され、フォールバック挙動のテスト green。
**コミット**: `fix(plan-q6 Step8 P2): gacha_service の到達不能 fallback を単一経路化 + CancelledError 誤捕捉を是正`

---

### Step 9: P2 — collection baseline の確定と prefetch の扱い確定（D4）

**対象**: `config/test_collection_baseline.json`、`src/integrations/semantic_cache.py:354-443`、
`tests/unit/integrations/prefetch/prefetch/test_semantic_prefetch_disabled.py`、`tests/unit/test_semantic_cache.py`

**変更**:
1. D1（Step 3）完了後の**確定値**に `config/test_collection_baseline.json` を更新する。
   - 現状 `9761`、HEAD ローカル実測 `9763`、計画 Q5 Step6 の受け入れ値 `9763`。
   - **現状値 9761 のままでは 2 件のテスト削除がゲートを通過できる**（現状のまま運用なら 9763 へ）。
   - `scripts/check_test_collection.py` は減少時のみ fail・増加時は baseline を更新しない方針を維持
     （Step 11 で returncode 検査を追加）。
2. D4 判断の記録:
   - **(a) 現状維持**の場合、`prefetch_next` の docstring（`semantic_cache.py:64-67`）に
     「プレースホルダ prompt で温めるため L1/L2 の実ヒットに寄与せず、既定 OFF」と**レビュー結論を追記**する。
     なお本差分で `build_drafting_prompt` の引数不足 `TypeError` が解消されたことにより、
     **OFF 時は従来どおり、ON 時は embedding API 呼び出しが発生する**点（コスト増）を明記する。
   - **(b) 削除**の場合、`PLAN_Q4_R2_BACKLOG.md` に削除タスクを登録し、本計画ではドキュメントのみ。

**根拠（実測）**: `_prefetch_embedding` は `_get_embedding` 経由で **L2-B（テキストハッシュ）のみ**を更新し、
`self._l1_cache` には一切書き込まない（`semantic_cache.py:434-443`）。L1 キーは
`sha256(f"{prompt}:{task_type}:{genre}:{temperature}")`（line 131-134）のため prompt が異なれば不一致。
追加済みテスト `test_semantic_cache_l1_key.py` は **search 側のキーワード一致のみ**を検証している
（prefetch/search の文字列一致は検証していない＝docstring 誠実に明記済み）。

**検証**:
```bash
.venv/bin/python scripts/check_test_collection.py          # rc=0（Step 3 完了後）
.venv/bin/python -m pytest tests/unit/test_semantic_cache.py \
  tests/unit/integrations/prefetch -q --timeout=120        # green
.venv/bin/python -m mypy src/integrations/semantic_cache.py
```
**受け入れ基準**: baseline が clean/ローカル実測と整合し、D4 の判断が本計画またはバックログに記録される。
**コミット**: `fix(plan-q6 Step9 P2): collection baseline を実測確定値へ + semantic prefetch の既定OFF方針を文書化 (D4)`

---

## Phase D: P3 — ドキュメント整合とゲートの検査強化（Step 10〜11）

### Step 10: P3 — ドキュメントの実態整合（レビュー指摘の残骸一掃）

**対象と変更**:

| 対象 | 変更 |
|---|---|
| `README.md:25` | 「mypy は 1122 → 952 に削減中（2026-11-30 までに半減目標 567）」を実態へ
（Step 4-(A) 採用時は「1122 → 450（warn 既定化後）、目標は JSON `targets` の mypy-half=500」）。
`README.md:24` の行頭日付「（2026-11-13 時点）」も実測日へ |
| `docs/SERVICES_ROOT_CLASSIFICATION.md:121` | 削除済み `prompt_registry.py` の現役行を「削除済み（Q5 Step5-A）」注記または削除 |
| `docs/MOVEMENT_MAPPING.md:34`（レビュー指摘） | 「`src/core/llm_clients` → `src/llm/clients` / **未着手**」の行が実態と矛盾（移動先 `src/llm/clients` は本差分で**削除済み**）。ステータスを「対象外（移動先ごと削除済み）」へ更新。同種の行は `docs/LLM_UNIFICATION_PLAN.md:76` にもあり併記 |
| `src/infrastructure/repositories/repo_prompt_metrics.py:26,29` | `PromptRegistry.get_metrics()` の言及を確認。⚠️ `src/domain/services/prompt_service.py:146` には**別クラスの `PromptRegistry` が現存**するため、削除済み `src/services/prompt_registry.py` を指す場合のみ更新する（指し先を必ず確認） |
| `plans/PLAN_Q5_DIFF_REVIEW_FIXES_10STEPS.md` | 受入値の乖離を実測で追記（mypy 計画 233 → 実測 234 / collection 計画 9763 → 実装 9761）、
**§D-3 の「pre-existing 9 項目」を実態へ更新**（base 23 / HEAD 19、うち 4 件は本差分で解消、**未記載 12 件**を追記） |
| `config/ci_lint_baseline.json` `history` | Step 4/5 の実測値変遷を 1 エントリ追記 |

**検証**:
```bash
# 削除済みモジュールへの言及（docs のみ。src 側は promptops 等の別物が存在するため対象を限定する）
grep -rn "services\.prompt_registry\|src/llm/clients\|src\.llm\.clients" docs/ README.md
grep -n "prompt_registry" docs/SERVICES_ROOT_CLASSIFICATION.md     # 削除済み注記が入ること
grep -n "ruff=[0-9]* / mypy=[0-9]* / format=[0-9]*" README.md       # JSON と一致（1 箇所のみ）
.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy             # rc=0
.venv/bin/python -c "import json;print(json.load(open('config/ci_lint_baseline.json'))['targets'])"  # README の目標記述と矛盾しないこと
```
**受け入れ基準**: README の表記が JSON `targets` / `history` と矛盾せず、削除済みモジュールの現役行が残らない。
> ⚠️ `src/domain/services/prompt_service.py:146` の別クラス `PromptRegistry` と
> `src/cli/promptops.py`（`src/promptops/prompt_registry.py` を生成する CLI）は**現存**するため、
> これらの言及は削除対象ではない。
**コミット**: `docs(plan-q6 Step10): README・分類表・計画書を実測値へ整合（D-3 の pre-existing 把握を実態に更新）`

---

### Step 11: P3 — 追加ゲート 2 本の検査強化

**対象**: `scripts/check_test_collection.py`、`scripts/check_untracked_imports.py`

**変更**:
1. `check_test_collection.py`:
   - `_collect_count()` 内で **`p.returncode` を検査**し、非 0（collection error 発生）なら
     件数によらず **exit 1** とする（現状は件数のみ比較のため、エラーファイル数が同数だと通過してしまう）。
   - `import re` を関数内からモジュール先頭へ移動（スタイル統一）。
2. `check_untracked_imports.py`:
   - `allowlisted_but_exists`（**陳腐化した allowlist エントリ**）を現行 WARN から
     `--strict` フラグで fail に切り替え、ci.yml のステップに `--strict` を付与する
     （現在 6 エントリのうち、`src.services.llm.prompts` など削除済み shim 由来が混在 → Step 10 と並行して精査）。
     ⚠️ **ci.yml への `--strict` 付与は allowlist 精査完了（Step 10 完了）後の follow-up コミット**とし、
     精査前に付けない（追加の CI 赤を避ける）。
   - 対象が `src.` 始まりのみである旨（`prompts.` 等は対象外）を docstring に明記し、拡張の要否を
     「スコープ外」へ記録する。

**根拠（実測）**: `check_untracked_imports.py` は通常実行で `OK`（rc=0）、allowlist は 6 エントリ。
`check_test_collection.py` は `_collect_count()` が returncode を一切見ない（ソース実測）。

**検証（感度は人手ではなくユニットテストで担保する）**:
```bash
.venv/bin/python scripts/check_test_collection.py            # rc=0
.venv/bin/python scripts/check_untracked_imports.py --strict # 陳腐化ゼロまで rc=0
.venv/bin/python -m pytest tests/unit/scripts -q --timeout=60   # 下記の新規テスト green
```
- 追加テスト `tests/unit/scripts/test_check_test_collection.py`（新規）:
  `subprocess.run` を `monkeypatch` で差し替え、`CompletedProcess(returncode=2, stdout="collected 9761 items")`
  を返す場合に **exit 1** になることを検証する（件数が一致していても落ちること）。
- 追加テスト `tests/unit/scripts/test_check_untracked_imports.py`（新規）:
  allowlist に「実在するモジュール」を 1 件だけ載せ、`--strict` で rc=1 / 通常実行で rc=0 になることを検証。

**受け入れ基準**: 2 スクリプトが通常実行 green、**「件数一致でも returncode != 0 → 赤」
「陳腐化 allowlist + --strict → 赤」の 2 つの感度がテストで実演される**。
**コミット**:
- `fix(plan-q6 Step11 P3): collection ゲートに returncode 検査を追加 + allowlist 陳腐化の --strict 化 + 感度テスト追加`
- （follow-up・Step 10 完了後）`ci(q6): check_untracked_imports に --strict を付与（allowlist 精査済み）`

---

## Step 12: 最終ゲート（総合検証）

```bash
# --- lint / 型 ---
.venv/bin/ruff check src tests config scripts                     # 0
.venv/bin/python scripts/ci_lint_ratchet.py --tool ruff           # rc=0
.venv/bin/python scripts/ci_lint_ratchet.py --tool format         # rc=0
.venv/bin/python scripts/ci_lint_ratchet.py --tool mypy           # rc=0（新 2 メトリクス）
.venv/bin/python scripts/check_untracked_imports.py --strict      # rc=0
.venv/bin/python scripts/check_layer_boundaries.py                # rc=0
README チェック（ci.yml line 49-65 のスニペット）                  # rc=0

# --- テスト ---
.venv/bin/python scripts/check_test_collection.py                 # rc=0
.venv/bin/python -m pytest -q -m "not integration and not perf and not slow" \
  -p no:randomly --timeout=120                                    # failed ≤ 19 件（回帰 0）/ passed ≥ 9301
.venv/bin/python -m pytest tests/security/test_H1_ci_workflow_contract.py -q  # 8 passed

# --- clean checkout での CI 再現（最重要） ---
git worktree add -f /tmp/opencode/q6_final HEAD
cd /tmp/opencode/q6_final
<venv> python scripts/ci_lint_ratchet.py --tool ruff && <venv> python scripts/ci_lint_ratchet.py --tool mypy \
  && <venv> python scripts/check_untracked_imports.py --strict && <venv> python scripts/check_layer_boundaries.py \
  && <venv> python scripts/check_test_collection.py               # 全 rc=0
cd - && git worktree remove --force /tmp/opencode/q6_final

# --- tree の清掃 ---
git status --short                                                 # 空（ratchet 実行で追跡ファイルが変化しないこと）
```

**受け入れ基準**:
1. 上記全コマンドが green。**unit フルスイートの failed が 19 件を超えない**（＝本計画での回帰 0）。
2. clean worktree で **P0 3 経路すべてが rc=0**。
3. 「不要 ignore を 1 件追加 → mypy ratchet が赤」「テストを 1 件削除 → collection ゲートが赤」の
   **感度実演**を各 1 回行い、一時変更を破棄する。
4. 各ステップが 1 コミットで分離され、コミットメッセージに実測根拠が書かれている。
5. Phase 0（D1〜D4）の判断が本計画 §1 に記録されている。

---

## コミット計画（12 件・1 ステップ = 1 コミット）

| # | コミットメッセージ | 依存 |
|---|---|---|
| 1 | `fix(plan-q6 Step1 P0): test_semantic_cache_l1_key の未使用 import を除去 (ruff 1->0)` | なし |
| 2 | `fix(plan-q6 Step2 P0): README チェックを ratchet より前へ移動 + 減少時保存の廃止 + --update が README 連動 (D2)` | なし |
| 3 | `fix(plan-q6 Step3 P0): settings.toml 欠如時のフォールバック生成で clean checkout の collection ゲートを緑化 (D1)` | D1 |
| 4 | `fix(plan-q6 Step4 P1): invalid-ignore を unused-ignore 実体化 (warn_unused_ignores 常時化, 1プロセス維持)` | D3 |
| 5 | `fix(plan-q6 Step5 P1): 本差分で混入した unused type-ignore 6 件を撤去 (216->210)` | 4 |
| 6 | `fix(plan-q6 Step6 P2): NarouExporter の len(Iterable) を list 化して ignore で隠していた実行時欠陥を解消` | なし |
| 7 | `fix(plan-q6 Step7 P2): UnitOfWork.commit を冪等化し outbox 二重 flush を予防 + テスト追加` | なし |
| 8 | `fix(plan-q6 Step8 P2): gacha_service の到達不能 fallback を単一経路化 + CancelledError 誤捕捉を是正` | なし |
| 9 | `fix(plan-q6 Step9 P2): collection baseline を実測確定値へ + semantic prefetch の既定OFF方針を文書化 (D4)` | 3, D4 |
| 10 | `docs(plan-q6 Step10): README・分類表・計画書を実測値へ整合（D-3 の pre-existing 把握を実態に更新）` | 2, 4, 5 |
| 11 | `fix(plan-q6 Step11 P3): collection ゲートに returncode 検査を追加 + allowlist 陳腐化の --strict 化 + 感度テスト追加`（ci.yml への `--strict` 付与は Step 10 完了後の follow-up コミット） | 3, 10 |
| 12 | `docs(plan-q6 Step12): 最終ゲート実行結果と残課題（unused 210 件・pre-existing 19 件）を記録` | 全 |

> 各コミット後に **必ず** `git checkout -- config/ci_lint_baseline.json tests/benchmarks/compression_baseline.json`
> のように、検証コマンドが書き換えた追跡ファイルが紛れていないか `git status --short` で確認する
> （Q5 リスク表の継承。Step 2-(b) 適用後は ratchet 側の書き込み自体が消える）。

---

## リスク

| リスク | 影響 | 緩和 |
|---|---|---|
| Step 4-(A) で `mypy_errors` が 234 → 450 に見える | 「床が上がった＝劣化」と誤読される | baseline JSON の `history` とコミットメッセージに「同一コード状態で warn の有無だけの差。劣化ではない」と明記 |
| Step 4-(A) 採用時に `warn_unused_ignores` が未知の unused を大量に露出する可能性 | 当初想定 216 件と異なり、実装後に別の件数が出る | Step 4 実装直後に `mypy src | grep -c unused-ignore` を再実測し、baseline を**その時点の実測**に置く（計画値 216 は参考値） |
| Step 2-(b)（減少時保存の廃止）で床の自動引き下げがなくなる | baseline が実測より緩いまま残る（250 vs 234） | 上限管理としては健全。床の引き下げは `--update`（Step 2-(c) で README も連動）で明示的に行う運用に切り替え |
| Step 3 が D1-(a) で解決しない（`_safe_load` 既存フォールバックとの干渉） | clean でも collection error が残る | 実装前に `validator.py:182` の挙動を確認。解決しない場合は D1-(b)/(d) へ即フォールバック |
| Step 7 の clear が「commit 後に stage した操作」を失わせる | ブロック内で commit → さらに stage → aexit で flush…の想定が壊れる | aexit は stage 内容をクリアする既存挙動のまま（clear は commit 成功時のみ）。追加テストで commit 後の stage → aexit flush を検証 |
| Step 11 の `--strict` が allowlist の陳腐化で CI を赤にする | 追加の CI 赤 | 陳腐化エントリの精査を Step 10 と並行実施し、**精査完了後に `--strict` を ci.yml へ付与**（順序をコミット計画で担保） |
| clean worktree 再現と実 CI（GitHub Actions）の差（Q5 D-4 の path hook リーク） | clean green でも CI が赤い可能性 | Step 12 の clean 検証は保守的近似であることを明記し、`gh` CLI 環境整備後に実 CI で最終確認（スコープ外） |

---

## スコープ外・別計画へ

| 項目 | 理由 | 接続先 |
|---|---|---|
| **残存 19 件の pre-existing テスト失敗**（うち 12 件は Q5 D-3 未記載） | e2e（settings.toml / `src.services.llm.prompts` 欠落）・perf/security の認証系・alembic head・orphan shims・順序依存 2 件とで原因系統が異なり、本計画のゲート回復と混在させるべきではない | 新規 `PLAN_Q7_PREEXISTING_TEST_FAILURES_*.md` を起案（Step 12 の報告を起点） |
| **unused ignore 残り 210 件のバーンダウン** | Step 5 は「本差分で混入した 6 件」のみ。残りは pre-existing | `config/ci_lint_baseline.json` の `targets` に `unused_ignore_errors` のバーンダウン target を追加（Step 4 で新設） |
| **`check_untracked_imports` の対象拡張（`src.` 以外、`prompts.` 等）** | 誤検出コストの見積が必要 | Step 11 で docstring 明記まで。実装はバックログ |
| **`ruff format --check src` の対象拡張（tests/config/scripts）** | リポジトリ全体で 936 ファイル再整形が必要（pre-existing） | `PLAN_R3_SHIM_REMOVAL_18STEPS.md` 等と並行する別計画 |
| **`config/settings.toml.example` の公開範囲・秘密情報設計** | セキュリティ判断を伴う | D1 の判断に含めてユーザー確認 |
| **実 CI（GitHub Actions）での最終確認** | `gh` CLI 未整備（`which gh` → 見つからず） | Q5 D-4 継承。環境整備後に別ステップ |
