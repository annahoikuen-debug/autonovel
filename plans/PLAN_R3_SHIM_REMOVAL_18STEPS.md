# PLAN_R3: shim 削除の安全化と再開 (18 STEPS)

> **目的**: `fee262b1` で発生した「参照解消を飛ばした shim 削除」による HEAD 破壊を復旧し、
> `docs/SHIM_REMOVAL_PLAN.md` の Phase R2 ゲート（旧パス参照数 == 0）を**機械的に強制**してから
> Phase R3 の削除バッチを安全に再開する。
>
> **前提文書**: `docs/SHIM_REMOVAL_PLAN.md`（R0-R4 の段階計画）/ `docs/CONFIG_UNIFICATION_PLAN.md`
> **現状（作成時点 / HEAD = `fee262b1`）**: `config/shim_registry.json` = 139 件（うち config/ 配下 23 件）
> **作業方針**: 1 ブランチ・直列実行。各 Step は独立して revert 可能なコミット単位。

---

## 0. 背景: 現在の障害

`fee262b1 feat: shim 削除 Phase R2+R3 (4件目): config/platform_censorship_rules.py` が
**旧パス参照を残したまま** shim を削除したため、HEAD が壊れている。

| 項目 | 内容 |
|------|------|
| 直接原因 | `formatters/erotic_censor.py:12` の `from config.platform_censorship_rules import get_censorship_rules` が `ModuleNotFoundError` |
| 影響（テスト） | `tests/unit/export/test_content_policy_gate.py` / `tests/integration/test_erotic_workflow.py` が collection error で中断 |
| 影響（本番） | `src/easy_mode/phase3/ebook_export.py:18` が `formatters.erotic_censor` を import → EPUB 書き出し経路が起動不能 |
| 検証 | `.venv/bin/python -c "import formatters.erotic_censor"` → `ModuleNotFoundError` |
| 根本原因 | 削除コミットの前に旧パス参照を一切確認していない（`SHIM_REMOVAL_PLAN` Phase R2 のゲートが手動・未実施）。コミット内容は shim 削除・registry・テストの 3 点のみで、参照置換の変更が含まれていない |

### 発見事項: 棚卸しスキャンの構造的な脆さ（再発防止の設計入力）

インシデント調査のための初回棚卸しは、トップレベル 11 ディレクトリのうち **3 ディレクトリ
（`prompts/` `schemas/` `frontend/`）を走査対象から漏らしていた**。実際にそこから見つかった旧パス参照:

- `prompts/commercial_prompts.py:10` → `from config.archetypes import ...`
- `prompts/manager.py:408, 656` → `from config.styles import get_rule_set`
- `prompts/registry.py` → `from config.settings import ...`
- `schemas/config.py` → `from config.validator import ...`

つまり「参照ゼロであることを確認する」行為自体も、**人手でルートを列挙する方式では破綻する**。
→ ゲート（Step 4）は `git ls-files` で追跡済み `.py` を全件列挙し、ルートの手動指定を禁止する。

---

## 1. 目的・スコープ

### 目的
1. HEAD の障害を復旧し、全テストを緑に戻す（Phase 0）
2. 「旧パス参照ゼロ」を機械検証するゲートを導入し、同じ事故を構造的に防ぐ（Phase 1）
3. 残存参照をカテゴリ別に解消し、config shim の削除を安全に完了する（Phase 2-3）
4. 生成物・ドキュメント・docstring の未整備点を同期する（Phase 4）

### スコープ内
- `config/` 配下の shim 23 件の参照解消と削除（SHIM_REMOVAL_PLAN の **R3-1**）
- ゲートテストとベースライン JSON の新規作成
- 既存の削除（1〜4 件目）の未整備点の解消

### スコープ外（別リリース）
- `src/services/` 系 shim（R3-2/R3-3/R3-4、現状 116 件）
- `config/shim_registry.json` 自体の削除（R4）
- 外部利用者向けの移行ガイド整備（CHANGELOG への記載のみ実施）

---

## 2. プリンシプル

| # | プリンシプル | 根拠 |
|---|-------------|------|
| P1 | **参照解消コミットと削除コミットを必ず分離する** | インシデントの直接原因 |
| P2 | **1 コミット = 1 shim**（同カテゴリのまとまりのみ例外） | revert 粒度の確保 |
| P3 | **ゲートは fail-closed**。違反があれば red。ルート列挙の余地を残さない（`git ls-files` 使用） | スキャン漏れが事故原因 |
| P4 | **ベースラインは集合一致**で比較する（増加も減少も fail） | 減少時にベースラインを自動的に引き下げる（ラチェットが自走する） |
| P5 | registry / `CONFIG_IMPORT_PATHS` / `REMOVED_SHIMS` の 3 箇所は同一コミットで同時更新 | 単一情報源の分散を防ぐ |
| P6 | 各 Step の完了条件は**コマンドと期待結果**で記述する | 主観的判断の排除 |
| P7 | 実行前に `git status` を確認し、並行作業と差分を混在させない | レビュー中の並行コミットで対象が移動した実例あり |

---

## 3. 前提データ: config shim 参照棚卸し

スキャン条件: `git ls-files '*.py'` 相当の全追跡 `.py`（2,801 ファイル、11 ルート）、
strict = `ast` による `from config.X` / `import config.X` の実 import 検出。

### 3-1. 参照ゼロ・削除可能（4 件）

| shim | 移設先 | 備考 |
|------|--------|------|
| `config/emotional_hook_vocabulary.py` | `src/config/emotional_hook_vocabulary.py` | `CONFIG_IMPORT_PATHS` のエントリ除去が必要 |
| `config/logging_config.py` | `src/infrastructure/config/logging_config.py` | 同上 |
| `config/narrative.py` | `src/domain/narrative.py` | 同上 |
| `config/streamlit_adapter.py` | `src/interfaces/streamlit_adapter.py` | `CONFIG_IMPORT_PATHS` に登録なし。`src/infrastructure/config/project_context.py` 等の docstring 表記のみ |

### 3-2. 参照あり・R2 解消が必要（19 件 / 63 エントリ）

| shim | 参照元ファイル数 | 参照元 |
|------|----------------|--------|
| `config/container.py` | 2 | `tests/unit/test_container.py`, `tests/unit/core/test_container.py` |
| `config/settings.py` | 2 | `prompts/registry.py`, `src/infrastructure/config/project_context.py` |
| `config/archetypes.py` | 1 | `prompts/commercial_prompts.py` |
| `config/archetypes_new.py` | 4 | `src/config/archetypes.py`, `src/backend/routers/misc.py`, `tests/contract/test_planning_options_contract.py`, `tests/unit/story_spine/test_removed_definitions.py` |
| `config/constants.py` | 4 | `src/engine/default_plot_expander.py`, `src/interfaces/streamlit_adapter.py`, `src/infrastructure/config/project_context.py`, `tests/regression/test_relative_episode_structure.py` |
| `config/domain_profile_manager.py` | 1 | `src/engine/bible_service.py` |
| `config/sharp_edge_vocabulary.py` | 2 | `src/backend/engine_plot.py`, `src/models/sharp_edge.py` |
| `config/project_context.py` | 19 | `src/backend/` 7, `src/agents/audit/` 2, `src/core/container/infra.py`, `src/infrastructure/config/project_context.py`, `src/interfaces/streamlit_adapter.py`, `src/llm/` 2, `src/services/pipeline_steps.py`, `streamlit_app/pages/` 2, `tests/` 2 |
| `config/validator.py` | 2 | `schemas/config.py`, `src/infrastructure/config/file_watcher.py` |
| `config/models.py` | 5 | `src/infrastructure/config/project_context.py`, `src/interfaces/streamlit_adapter.py`, `streamlit_app/pages/` 2, `tests/config/test_project_context_integrity.py` |
| `config/styles.py` | 1 | `prompts/manager.py`（2 箇所） |
| `config/erotic_direct_mappings.py` | 2 | `formatters/erotic_censor.py`, `src/engine/prompts/erotic_specialist.py` |
| `config/erotic_pacing.py` | 5 | `src/engine/prompts/erotic_specialist.py`, `src/backend/workflows/refine_erotic_workflow.py`, `tests/` 3 |
| `config/erotic_parameters.py` | 2 | `src/engine/prompts/erotic_specialist.py`, `src/agents/erotic/curve.py` |
| `config/erotic_platform_presets.py` | 3 | `formatters/erotic_censor.py`, `src/engine/prompts/erotic_specialist.py`, `tests/integration/test_erotic_workflow.py` |
| `config/erotic_thresholds.py` | 3 | `src/engine/audit/service.py`, `src/domain/services/erotic_afterglow_evaluator.py`, `src/domain/services/erotic_diversity_score.py` |
| `config/erotic_video_patterns.py` | 1 | `src/engine/prompts/erotic_specialist.py` |
| `config/erotic_vocabulary.py` | 3 | `formatters/erotic_censor.py`, `src/engine/prompts/erotic_specialist.py`, `tests/integration/test_erotic_workflow.py` |
| `config/erotic_vocabulary_ext.py` | 1 | `tests/integration/test_erotic_workflow.py` |

### 3-3. 特記事項

- **レイヤー違反**: `src/config/archetypes.py:4` が `from config.archetypes_new import *` —
  新パス（実体）が旧パス（shim）に依存している。Step 11 で `src.config.archetypes_new` へ直す。
- **参照集中**: `src/engine/prompts/erotic_specialist.py` が 6 shim、
  `formatters/erotic_censor.py` が 3 shim、`tests/integration/test_erotic_workflow.py` が 4 shim を
  旧パスで参照。Step 13 で一括置換すると効率が良い。
- **既知の削除済み 5 件**（`image_models` / `imagen_models` / `cors_config` / `file_watcher` /
  `platform_censorship_rules`）は Step 6 の削除検出テストに登録する。

---

## 4. ステップ詳細

### Phase 0: 障害復旧（Steps 1-3）

#### Step 1: `formatters/erotic_censor.py` の旧パス import を解消

- **対象**: `formatters/erotic_censor.py:12`
- **変更**:
  ```diff
  -from config.platform_censorship_rules import get_censorship_rules
  +from src.config.platform_censorship_rules import get_censorship_rules
  ```
- **同ファイル内の docstring 表記も更新**: 4 行目・19 行目の
  `config/platform_censorship_rules.py` → `src/config/platform_censorship_rules.py`
- **完了条件**:
  ```bash
  .venv/bin/python -c "import formatters.erotic_censor"           # exit 0
  .venv/bin/python -m pytest tests/unit/export/test_content_policy_gate.py \
      tests/integration/test_erotic_workflow.py -q                 # 2 passed 以上
  ```
- **コミット**: `fix(shim): formatters/erotic_censor の旧パス import を解消し HEAD の collection error を復旧`

#### Step 2: 既存削除（1〜4 件目）の未整備点を解消

- **対象**:
  | ファイル | 変更 |
  |---------|------|
  | `src/publishing/illustration/model_selector.py:5` | docstring の「必ず config.imagen_models を経由する」→ `src.config.imagen_models` |
  | `src/publishing/illustration/image_service.py:22` | docstring の「config.imagen_models を介して」→ `src.config.imagen_models` |
  | `docs/CONFIG_UNIFICATION_PLAN.md:31-32` | 削除済み shim の行を「削除済み（R3-1/2/4）」に更新 |
  | `tests/regression/test_shim_deprecation_warning.py:26` | docstring の「141 件（現行）」→ 実数に合わせた表現へ（例: 「現行件数であること」） |
- **完了条件**: `grep -rn "config\.imagen_models" src/ tests/` が docstring の新パス表記のみを返す
- **コミット**: `docs: 削除済み config shim に関する docstring・計画書表を実態に同期`

#### Step 3: 回帰確認と Phase 0 クローズ

- **完了条件**:
  ```bash
  git status --short                    # clean
  .venv/bin/python -m pytest tests/regression/ -q --timeout=120   # 全緑（現状 194 件超）
  .venv/bin/python -m pytest tests/unit/export/ -q                # 全緑
  ```

---

### Phase 1: R2 ゲートの自動化（Steps 4-8）

#### Step 4: ゲートテスト新規作成

- **成果物**: `tests/regression/test_shim_reference_gate.py`
- **設計**（P3/P4 を実装）:
  ```python
  """R2 ゲート: 各 shim の旧パス参照がベースラインと一致することを強制する。

  - 増加: 新しい旧パス参照が出たら fail（削除前の R2 達成を強制）
  - 減少: 参照が解消されたら fail（ベースライン引き下げを促し、ラチェットが自走する）
  - スキャン範囲: git ls-files で追跡済み .py を全件列挙（ルートの手動列挙を禁止）
  """
  ```

- **検出方式（2 段階）**:
  1. **strict**: `ast` で `ast.Import` / `ast.ImportFrom` を走査し `from config.X` / `import config.X` を検出
  2. **loose**: ソース全体の文字列に `config.X` が含まれるものを検出
     （`importlib.import_module("config.X")` や `monkeypatch.setattr("config.X.y", ...)` を拾うため）
  - strict 違反は無条件 fail。loose のみの一致はベースラインの `mentions` として登録対象
- **実装上の落とし穴（必ず対処すること）**:
  - **`src.config.X` が `config.X` の部分文字列として一致する** → `src.` 等の接頭辞を
    negative lookbehind（`(?<![\w.])config\.X`）で除外しないと、新パスの参照を全部誤検出する
  - 同様に `config.X_y` が `config.X` に一致しないよう境界 `\b` を付ける
  - パッケージ名の prefix 衝突（`config.models` と `config.models_hoge`）も境界で防ぐ
- **ファイル列挙**: `git ls-files -z -- '*.py'` を使用し、カレントの追跡ファイルと一致させる。
  `git` が無い環境（アーカイブ展開等）のみ `pytest.skip` とし、CI に git が必須であることは
  `tests/security/test_H1_ci_workflow_contract.py` で担保する（CI 上は常に fail-closed）
- **完了条件**: 現状の 63 エントリでテストが green（Step 5 のベースライン作成後）

#### Step 5: ベースライン JSON 作成

- **成果物**: `config/shim_reference_baseline.json`（既存の `ci_lint_baseline.json` /
  `layer_boundaries_baseline.json` と同じ運用）
- **形式**（参照元は**ファイル一覧**で保持し、集合一致で比較する）:
  ```json
  {
    "baseline_commit": "<作成時コミット SHA>",
    "scan_note": "git ls-files で全追跡 .py を走査する（ルート手動列挙禁止）",
    "violations": {
      "config/project_context.py": {
        "files": [
          "src/backend/engine_critique.py",
          "src/backend/patch_validator.py"
        ],
        "reason": "旧パス参照が src/backend 以下 19 ファイルに残存（Phase R2 未完了）",
        "todo": "TODO(R3-12)"
      }
    }
  }
  ```
- **比較ルール**: 実際の参照元ファイル集合と `files` の**完全一致**を要求する
  - 実際が多い → 新規違反（R2 未達のまま削除しようとしている）→ fail
  - 実際が少ない → 参照解消済み（ベースラインが古い）→ fail して引き下げを促す
- **必須属性**: 各エントリに `reason`（日本語）と `todo`（`TODO(R3-NN)` 形式の番号）。
  ゲート側で欠落を fail させる（`test_H1_tautology_guard` と同様の「理由なし例外禁止」運用）
- **`mentions`（任意キー）**: strict import では拾えないが文字列に `config.X` が含まれる
  ファイル（docstring・`monkeypatch.setattr` の文字列パス等）を同様に集合で保持し、
  同じ増減ルールで比較する
- **検証の容易さ**: `count` ではなく `files` を持たせるため、fail メッセージに
  「追加すべき/削除すべきファイル」をそのまま列挙できる
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_shim_reference_gate.py -q   # green
  ```

#### Step 6: 削除検出テスト新規作成（SHIM_REMOVAL_PLAN 手順 4 の実装）

- **成果物**: `tests/regression/test_shim_removal_detection.py`
- **登録対象（REMOVED_SHIMS）**: 既に削除済みの 5 件
  `config/image_models.py`, `config/imagen_models.py`, `config/cors_config.py`,
  `config/file_watcher.py`, `config/platform_censorship_rules.py`
- **各エントリについて 3 点を assert**:
  1. ファイルが存在しない
  2. 旧パスが `ModuleNotFoundError` で import 失敗する
  3. `config/shim_registry.json` に未登録
- **加えて（今回の事故の中核）**: `REMOVED_SHIMS` の旧パスを参照するソースが
  **1 ファイルも無いこと**を assert する。これは `fee262b1` を 1 コミットで検出できる
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_shim_removal_detection.py -q  # green
  # 意図的に formatters/erotic_censor.py の import を旧パスに戻すと red になること（手動検証後に戻す）
  ```

#### Step 7: 削除予定と競合する既存テストの整理

- **対象と変更**:
  | ファイル | 変更 |
  |---------|------|
  | `tests/regression/test_shim_deprecation_warning.py:66` | dynamic 候補の `"config.archetypes"` を、本計画のスコープ外で残存する shim（例 `src.backend.config`）へ差し替え。config 系の shim は Phase 2 で全件削除するため、config 系の候補は残さない |
  | `tests/regression/test_config_unification_complete.py:47-65` | Step 9 で削除する 4 件のエントリは **Step 9 の同一コミットで**除去（本 Step では触らない） |
- **補足**: `test_no_orphan_config_files` の `moved_files` から削除済みエントリを消さない。
  ファイル不在なら `path.exists()` でスキップされ、実体の復活を検知できるラチェットとして機能する
- **完了条件**: `.venv/bin/python -m pytest tests/regression/test_shim_deprecation_warning.py -q` が green

#### Step 8: CI 配線の確認

- `tests/regression/` は `.github/workflows/ci.yml` の
  `pytest tests/regression/ -v --timeout=120` で自動実行されているため、**追加ジョブ不要**
- CI 契約自体は `tests/security/test_H1_ci_workflow_contract.py` が担保
- **完了条件**: 作成した 2 テストがローカルで red → green になることを確認し、
  あらかじめ 1 件、意図的に red にして CI が拾うことを確認する（確認後に元に戻す）

---

### Phase 2: 残存参照の解消 — config システム（Steps 9-14）

> 各 Step の**標準手順**（P1/P2/P5）:
> 1. **参照解消コミット**: 参照元の import を新パスへ置換し、
>    `config/shim_reference_baseline.json` の該当エントリ（参照元ファイル一覧）も同じコミットで更新。
>    ゲートは「減少でも fail」するため、この同時更新を省略すると green にならない
> 2. ゲート + 関連テストが green であることを確認
> 3. **削除コミット**で以下を同一にまとめる:
>    - `git rm` で shim を削除
>    - `config/shim_registry.json` から該当エントリを除去
>    - `tests/regression/test_config_unification_complete.py` の `CONFIG_IMPORT_PATHS` から除去（登録がある場合）
>    - `tests/regression/test_shim_imports.py` の `KNOWN_SHIMS` から除去（登録は `config.container` と `config.erotic_vocabulary` の 2 件のみ）
>    - `tests/regression/test_shim_removal_detection.py` の `REMOVED_SHIMS` に追加
>    - `config/shim_reference_baseline.json` から該当エントリを丸ごと除去
>    - `test_no_orphan_config_files` の `moved_files` からは**除去しない**（Step 7 の方針）
> 4. ゲート + 全関連テストが green であることを確認

#### Step 9: 参照ゼロ 4 件を削除（R3-1 の最初の安全分）

- **対象**: `config/emotional_hook_vocabulary.py`, `config/logging_config.py`,
  `config/narrative.py`, `config/streamlit_adapter.py`
- **手順**: 標準手順の 3 のみ。ただし `config.streamlit_adapter` だけは **docstring 中の
  旧パス表記が 3 箇所**残っており、削除検出テスト（loose 検出）で fail するため先に解消する:

  | ファイル | 行 | 変更 |
  |---------|----|------|
  | `src/llm/model_router.py` | 65 | `` `config.streamlit_adapter` `` → `src.interfaces.streamlit_adapter` |
  | `src/infrastructure/config/project_context.py` | 14 | `config.streamlit_adapter` → `src.interfaces.streamlit_adapter` |
  | `src/infrastructure/config/project_context.py` | 93 | `config.streamlit_adapter.StreamlitConfig` → `src.interfaces.streamlit_adapter.StreamlitConfig` |

  他の 3 件の旧パス参照は `test_config_unification_complete.py` の
  `CONFIG_IMPORT_PATHS`（51 / 53 / 59 行）のみ。
- **手順の残り**: `CONFIG_IMPORT_PATHS` から 3 件（`emotional_hook_vocabulary` / `logging_config` /
  `narrative`）を除去。`moved_files` からの除去は**しない**（Step 7 の方針）
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_config_unification_complete.py \
      tests/regression/test_shim_reference_gate.py \
      tests/regression/test_shim_removal_detection.py \
      tests/regression/test_new_shims_registered.py -q      # green
  ```
- **コミット**: `feat: shim 削除 Phase R2+R3 (5件目): config/{emotional_hook_vocabulary,logging_config,narrative,streamlit_adapter}.py`
  （1 shim 1 コミットに厳密にする場合は 4 コミットに分割。P2 に従う）

#### Step 10: 低参照数 5 件の参照解消 → 削除

| shim | 置換対象 |
|------|---------|
| `config/archetypes.py` | `prompts/commercial_prompts.py:10` |
| `config/styles.py` | `prompts/manager.py:408, 656` |
| `config/validator.py` | `schemas/config.py`, `src/infrastructure/config/file_watcher.py` |
| `config/domain_profile_manager.py` | `src/engine/bible_service.py` |
| `config/settings.py` | `prompts/registry.py`, `src/infrastructure/config/project_context.py` |

- **注意**: `prompts/` と `schemas/` は**従来のスキャンから漏れていたルート**。
  置換後、ゲートが green であることを必ず確認する（漏れの残存をゲートが検出する）
- **完了条件**: 各 shim について `shim_reference_baseline.json` のエントリが消え、ゲート green

#### Step 11: 中規模 5 件の参照解消 → 削除

| shim | 置換対象 | 特記事項 |
|------|---------|---------|
| `config/archetypes_new.py` | 4 ファイル | **`src/config/archetypes.py:4` のレイヤー違反を同時に解消**（`src.config.archetypes_new` へ） |
| `config/constants.py` | 4 ファイル | `streamlit` 経路を含むため `tests/regression/test_relative_episode_structure.py` を同コミットで実行 |
| `config/sharp_edge_vocabulary.py` | 2 ファイル | |
| `config/container.py` | 2 ファイル | `tests/unit/test_container.py` / `tests/unit/core/test_container.py` |
| `config/models.py` | 5 ファイル | `streamlit_app/pages/` 2 ファイルを含む |

- **完了条件**: 上記テスト + ゲート green。レイヤー違反の修正は
  `src/config/archetypes.py` の import を `from src.config.archetypes_new import *` に変更した
  コミットとして分離し、`tests/contract/test_planning_options_contract.py` を実行

#### Step 12: `config/project_context.py`（19 ファイル）の参照解消

- **分割方針**（1 コミット巨大化の回避、P2 の例外は「同レイヤーまとまり」のみ）:
  | 仮 | 対象 | 確認テスト |
  |----|------|-----------|
  | 12a | `src/backend/`（7 ファイル） | `pytest tests/unit/backend/ -q` |
  | 12b | `src/core/container/infra.py`, `src/infrastructure/config/project_context.py`, `src/interfaces/streamlit_adapter.py`, `src/llm/` 2, `src/services/pipeline_steps.py`, `src/agents/audit/` 2（計 8） | `pytest tests/unit/ -q -k "model_router or pipeline_steps or container"` |
  | 12c | `streamlit_app/pages/`（2）+ `tests/`（2） | `pytest tests/config/test_project_context_integrity.py -q` |
  | 12d | shim 削除 + registry / `CONFIG_IMPORT_PATHS` / `REMOVED_SHIMS` 更新 | ゲート + `test_config_unification_complete` |
- **完了条件**: ゲートの `config/project_context.py` エントリが消える

#### Step 13: erotic 系 8 件の参照解消 → 削除

- **集中置換のポイント**（3 ファイルで 13 エントリを解消できる）:
  | ファイル | 置換対象の shim |
  |---------|---------------|
  | `src/engine/prompts/erotic_specialist.py` | `erotic_direct_mappings`, `erotic_pacing`, `erotic_parameters`, `erotic_platform_presets`, `erotic_video_patterns`, `erotic_vocabulary`（6 件） |
  | `formatters/erotic_censor.py` | `erotic_direct_mappings`, `erotic_platform_presets`, `erotic_vocabulary`（3 件） |
  | `tests/integration/test_erotic_workflow.py` | `erotic_pacing`, `erotic_platform_presets`, `erotic_vocabulary`, `erotic_vocabulary_ext`（4 件） |
- **残り**: `src/backend/workflows/refine_erotic_workflow.py`, `src/agents/erotic/curve.py`,
  `src/engine/audit/service.py`, `src/domain/services/erotic_{afterglow_diversity}_evaluator.py`,
  `src/domain/services/erotic_diversity_score.py`, `tests/regression/test_nsfw_opt_in.py`,
  `tests/unit/easy_mode/test_erotic_specialist_prompts.py`
- **登録簿の同時更新（見落としやすい）**:
  - `tests/regression/test_shim_imports.py:20` の `KNOWN_SHIMS` から `config.erotic_vocabulary` を除去
  - `tests/regression/test_config_unification_complete.py:65` の
    `("config.erotic_vocabulary", ["METAPHOR_BANK"])` を除去
  - `config/shim_registry.json` の erotic 8 エントリを除去
- **確認テスト**: `pytest tests/integration/test_erotic_workflow.py tests/regression/test_nsfw_opt_in.py tests/unit/easy_mode/ -q`
- **完了条件**: ゲートの erotic エントリが全て消える

#### Step 14: ベースライン引き下げの完了確認

- **完了条件**:
  ```bash
  .venv/bin/python -c "import json;print(list(json.load(open('config/shim_reference_baseline.json'))['violations']))"
  # → config/ 配下の shim が 1 件も無いこと（src/ 系のエントリは Phase 2 スコープ外なので残ってよい）
  .venv/bin/python -m pytest tests/regression/ -q --timeout=120   # 全緑
  ```
- **コミット**: `feat: config shim の Phase R2 参照解消を全件完了（baseline から config/ を消却）`

---

### Phase 3: 削除バッチの運用定着（Steps 15-16）

#### Step 15: `docs/SHIM_REMOVAL_PLAN.md` の削除手順をゲート必須化

- **変更箇所**: 「削除時の実装手順（各バッチ共通）」に以下を**先頭**として追記
  1. `pytest tests/regression/test_shim_reference_gate.py -q` が green（該当 shim の
     baseline エントリが無いこと）
  2. `pytest tests/regression/test_shim_removal_detection.py` に当該 shim を `REMOVED_SHIMS` へ追加
- **併せて更新**: §4 進捗チェックリストの `R2` / `R3-1` のステータス
  （R2 は config カテゴリのみ完了、services 系は未完了、と正確に記載）
- **完了条件**: 手順書にゲート必須化の記載があり、再現コマンドが書かれている

#### Step 16: R3-1 完了の宣言と件数同期

- **変更対象**:
  | ファイル | 変更 |
  |---------|------|
  | `config/shim_registry.json` | `config/` 配下のエントリが 0 件になる（Step 9-13 で 23 件全て削除済み）。残るのは `src/` 系のみ |
  | `docs/CONFIG_UNIFICATION_PLAN.md` | config/ の shim 表を「削除済み」に |
  | `docs/MOVEMENT_MAPPING.md` | Phase 3（Steps 21-27）のステータス更新 |
  | `CHANGELOG.md` | `[Unreleased]` に「config shim の削除と旧パス参照の解消（R3-1）」+ 移行ガイド（`config.X` → `src.config.X` の対応表） |
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/ tests/unit/ -q --timeout=120   # 全緑
  ```

---

### Phase 4: 生成物・ドキュメント同期（Steps 17-18）

#### Step 17: `var/import_graph.json` の再生成と鮮度テスト

- **手順**: `.venv/bin/python scripts/generate_import_graph.py`
- **成果物**: `tests/regression/test_import_graph_freshness.py`
  - 生成スクリプトを再実行し、`var/import_graph.json` に差分が出ないこと（git diff で検証）
  - 生成物が存在しない／追跡対象外の場合は fail
- **根拠**: 現状 `var/import_graph.json:40` に削除済みの `"config/imagen_models.py"` が残存し、
  鮜度を検証するテストが無い（`docs/LLM_UNIFICATION_PLAN.md:84-86` が移動前の検証手段として
  このファイルを推奨しているため、鮮度が無いと手段自体が無効）
- **完了条件**: 再生成後に `git diff --stat var/import_graph.json` が空、テスト green

#### Step 18: 残存ドキュメント・docstring の最終同期

- **変更対象**:
  | ファイル | 内容 |
  |---------|------|
  | `docs/SHIM_REMOVAL_PLAN.md` | §1 現状表の件数（141 → 実数）、§4 チェックリスト |
  | `docs/PLAN_C_SUMMARY.md:60` | 「141 shim 登録」の記載を実数に |
  | `plans/PLAN_B_LAYER_REORGANIZATION_36STEPS.md` | 履歴文書のため**更新しない**（過去の記録として残す） |
- **最終確認（Step 2 の対象 docstring を含めて漏れが無いこと）**: 既存削除分の
  `src/publishing/illustration/model_selector.py:5` / `image_service.py:22` もここで再確認する
- **完了条件**:
  ```bash
  grep -rn "config\.imagen_models\|config\.platform_censorship_rules" src/ tests/ formatters/ prompts/ schemas/
  # → 新パス（src.config.*）の記述のみ、または無し
  ```

---

## 5. テスト計画

### 5-1. 新規テスト

| テスト | 用途 | Phase |
|--------|------|-------|
| `tests/regression/test_shim_reference_gate.py` | 旧パス参照の集合がベースラインと一致（増加/減少とも fail） | 1 |
| `tests/regression/test_shim_removal_detection.py` | 削除済み shim が import 不可・未登録・参照ゼロ | 1 |
| `tests/regression/test_import_graph_freshness.py` | 生成物の鮮度 | 4 |

### 5-2. 各 Phase の完了確認コマンド

```bash
# Phase 0
.venv/bin/python -c "import formatters.erotic_censor"
.venv/bin/python -m pytest tests/unit/export/ tests/integration/test_erotic_workflow.py -q
.venv/bin/python -m pytest tests/regression/ -q --timeout=120

# Phase 1
.venv/bin/python -m pytest tests/regression/test_shim_reference_gate.py \
    tests/regression/test_shim_removal_detection.py \
    tests/regression/test_shim_deprecation_warning.py \
    tests/regression/test_shim_usage_stats.py \
    tests/regression/test_new_shims_registered.py -q

# Phase 2（各 Step 後）
.venv/bin/python -m pytest tests/regression/ -q --timeout=120
.venv/bin/python -m pytest tests/unit/ -q -m "not integration and not perf and not slow" --timeout=120

# Phase 3-4（リリース前）
.venv/bin/python -m pytest tests/regression/ tests/unit/ tests/security/ -q --timeout=120
.venv/bin/python -m pytest tests/integration -q --timeout=180
.venv/bin/python -m ruff check src/config src/publishing formatters prompts schemas
```

### 5-3. CI との関係

- `tests/regression/` は CI の `Run v5 regression guardrails` で自動実行 → 追加ジョブ不要
- `tests/unit/` は `--cov-fail-under=60` 付きで実行 → カバレッジ低下に注意
- `tests/security/test_H1_ci_workflow_contract.py` が CI 契約を担保

---

## 6. リスクとロールバック

| リスク | 影響 | 対策 | ロールバック |
|--------|------|------|-------------|
| 大量の import 置換による回帰 | 各レイヤーのテスト失敗 | Step ごとに分割し、当該レイヤーのテストを同コミットで実行 | 該当コミットを `git revert` |
| スキャンルートの再漏れ | 再び削除事故 | `git ls-files` で追跡 .py 全件を走査（ルート手動列挙を禁止） | — |
| ベースラインの過大登録でゲートが形骸化 | 事故が見えない | 集合一致比較 + `reason`/`todo` 必須アサーション + 件数の trend を CI ログに出す | — |
| 並行作業との差分混在 | 対象が移動・上書き | P7: 実行前に `git status` 確認、作業中のブランチを固定 | `git stash` / worktree 分離 |
| 外部利用者が旧パスを利用 | 破壊的変更 | 既存の `DeprecationWarning` + CHANGELOG の移行ガイド（Step 16） | シムを復元（`git revert`） |
| `streamlit_app/` など UI 経路の取りこぼし | UI の起動不能 | Step 12c で個別にテスト、ゲートが `streamlit_app/` を走査対象に含める | 該当コミットを `git revert` |
| erotic 系の一括置換での取りこぼし | コンテンツ生成経路の障害 | Step 13 の集中置換表 + `test_erotic_workflow` / `test_nsfw_opt_in` を同コミットで実行 | 該当コミットを `git revert` |

---

## 7. 成果物一覧

### 新規ファイル
- `tests/regression/test_shim_reference_gate.py`
- `tests/regression/test_shim_removal_detection.py`
- `tests/regression/test_import_graph_freshness.py`
- `config/shim_reference_baseline.json`

### 修正対象（カテゴリ別・概数）
| カテゴリ | 件数 | 内容 |
|---------|------|------|
| 障害復旧 | 1 ファイル | `formatters/erotic_censor.py` |
| shim 削除 | 23 ファイル | `config/` 配下の全 shim |
| 参照置換 | 45 ファイル | 63 エントリ（ユニーク参照元: `src/` 28, `tests/` 10, `prompts/` 3, `streamlit_app/` 2, `schemas/` 1, `formatters/` 1） |
| 登録簿 | 4 ファイル | `shim_registry.json` / `test_config_unification_complete.py` / `test_shim_imports.py` / `test_shim_deprecation_warning.py` |
| ドキュメント | 5 ファイル | `SHIM_REMOVAL_PLAN.md` / `CONFIG_UNIFICATION_PLAN.md` / `MOVEMENT_MAPPING.md` / `PLAN_C_SUMMARY.md` / `CHANGELOG.md` |
| 生成物 | 1 ファイル | `var/import_graph.json` |

---

## 8. 完了条件（DoD）

- [ ] HEAD が green（`pytest tests/regression/ tests/unit/ tests/security/` 全緑、collection error なし）
- [ ] `config/` 配下の shim が 0 件（`shim_registry.json` に `config/` エントリが無い）
- [ ] `config/shim_reference_baseline.json` の `violations` / `mentions` に `config/` 配下の shim が 1 件も無い
- [ ] `tests/regression/test_shim_removal_detection.py` が削除済み 23+5 件を検証している
- [ ] 旧パス参照が残る shim には `reason` と `TODO(R3-NN)` が登録されている（services 系のみ）
- [ ] `docs/SHIM_REMOVAL_PLAN.md` の R2/R3-1 が正確なステータスになっている
- [ ] `var/import_graph.json` が鮮度テスト付きで再生成済み
- [ ] `CHANGELOG.md` に移行ガイド（`config.X` → `src.config.X` 対応表）がある
- [ ] `grep -rn "config\.imagen_models\|config\.platform_censorship_rules" src/ tests/ formatters/ prompts/ schemas/`
      が新パスの記述のみを返す

---

## 9. 見積り目安

| Phase | Step | 規模 | 目安 |
|-------|------|------|------|
| 0 | 1-3 | 小 | 0.5 日 |
| 1 | 4-8 | 中 | 1 日（ゲートの検出方式の詰めが主） |
| 2 | 9-14 | 大 | 3 日（Step 12 の 19 ファイルと Step 13 の erotic 8 件が主） |
| 3 | 15-16 | 小 | 0.5 日 |
| 4 | 17-18 | 小 | 0.5 日 |
| **計** | **18** | | **5.5 日（目安）** |
