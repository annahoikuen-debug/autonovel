# PLAN_Q3: shim 焼却 — R3-2/R3-3/R3-4 の実行 (16 STEPS)

> **目的**: `config/shim_registry.json` 登録 116 件（R3-1 の config/ 23 件は完了済み）のうち、
> 実運用トラフィック上位の shim を「参照解消 → 削除 → 復活検出」のサイクルで撤去し、
> 最終的に **import 時 `DeprecationWarning` をゼロにする**。あわせて
> `src/models/db.py` 型の二重定義（本番が非推奨側を使っている逆転）を解消する。
>
> **実測日**: 2026-11-15（参照数は `git ls-files` 全追跡 `.py` に対する正規表現スキャンの実測。
> 計画実行時は Step 1 のスクリプトで再計測し、本表を上書きしてよい）
> **前提**: `PLAN_Q1`（ゲート緑化）・`PLAN_Q2`（デッドコード削除）が完了していること。
> Q2 により `src/core/llm_clients/__init__.py`（参照 10 件）は既に消えている。
> **前提文書**: `docs/SHIM_REMOVAL_PLAN.md`（R0-R4）/ `plans/PLAN_R3_SHIM_REMOVAL_18STEPS.md`（本計画はその R3-2 以降の実行計画）
> **作業方針**: PLAN_R3 P1-P7 を全面継承。1 ブランチ・直列実行。

---

## 1. 実測データ（2026-11-15 時点）

### 1-1. shim 登録状況

- `config/shim_registry.json`: **116 件**（`updated_at: 2026-11-06`）。`config/` 配下は 0 件 → **R3-1 完了済み**
- 内訳: `services` 90 / `backend` 5 / `api` 4 / `core` 3 / `engine` 3 / `domain` 2 / `models` 2 / `agents` 2 / `schemas` 1 / 他 4
- import 時 `DeprecationWarning` を発するモジュール: **122 件**（`grep -l DeprecationWarning src --include="*.py"` 実測）

### 1-2. トラフィック順 shim 参照数（上位 12 件、src 参照 / 全参照）

| shim | 移設先（registry・docstring 実測） | src | all |
|---|---|---:|---:|
| `src/backend/config.py` | `src.infrastructure.config.settings` | **57** | 101 |
| `src/services/llm/__init__.py` | `src.llm.adapters` 系 | **28** | 47 |
| `src/backend/database/core.py` | `src.infrastructure.database.*` | **14** | 35 |
| `src/llm/service.py` | `src.llm.*` | **13** | 18 |
| `src/services/llm/factory.py` | `src.llm.adapters.factory` | **12** | 13 |
| `src/agents/audit_agent.py` | `src.agents.audit_agent`（パッケージ） | 9 | 21 |
| `src/agents/audit.py` | `src.agents.audit`（パッケージ） | 7 | 12 |
| `src/engine/book_score/service.py` | `src.engine.book_score.calculator` 系 | 6 | 21 |
| `src/engine/book_score/mapping.py` | 同上 | 5 | 8 |
| `src/models/db.py` | `src.domain.models.*` | **5** | 7 |
| `src/services/llm/prompts.py` | `src.llm.adapters.prompt_cache` 系 | 4 | 6 |
| `src/backend/logging_config.py` | `src.infrastructure.logging_config` | 4 | 6 |

### 1-3. 参照ゼロ shim（即時削除候補 25 件）

`src/services/{rag,publishing,publishers,prose,prefetch,observability,narrative,manga,illustration,graph,formatters}/__init__.py` ほか、
`src/services/llm/{vllm,claude,ollama}_adapter.py`・`provider_failover.py` 等（Step 1 の再計測で最終確定）。

### 1-4. 特記事項（技術的リスクの実測）

1. **同名ファイル / パッケージ衝突（shadowing）**: `src/agents/audit.py`・`src/agents/audit_agent.py`・`src/services/marketing.py` は、
   同名の**パッケージ**が存在するため import 解決で到達不能（`importlib.util.find_spec` 実測:
   `src.agents.audit` → `src/agents/audit/__init__.py`）。**これらは参照解消なしで削除できる**
   （regex スキャンの「参照 7 件 / 9 件」は実行時には解決しない文字列一致である点に注意）。
   同型の衝突が他にも無いかを Step 2 で機械検出する。
2. **二重定義の逆転**: `PlotDbModel` / `ChapterDbModel` が `src/models/db.py:90,160` と
   `src/domain/models/{plot:19,chapter:12}` に二重定義。**本番 5 ファイル（`src/core/interfaces.py:9` 等）は
   非推奨側 `src.models.db` を import**（import 時 DeprecationWarning を毎回発火）。後方互換シムの意味が
   逆転している（新パス側が誰にも使われていない）。
3. **実体が docstring で誤誘導**: `src/models/db.py:7` など実コードなのに「docs/MOVEMENT_MAPPING.md を参照」
   という DeprecationWarning を出す例が複数（Q1 評価で確認済み）。本計画では「警告を消す」ではなく
   **参照を新パスに寄せて警告自体をゼロ**にする。

---

## 2. 目的・スコープ

### 目的
1. shim 116 件をトラフィック順に撤去し、**registry を空（または最小）にする**
2. `src/models/db.py` の二重定義を新パス（`src.domain.models`）に統一し、**本番 import から DeprecationWarning を消す**
3. 「import 時 DeprecationWarning ゼロ」の**常設ゲート**を新設する
4. shim 削除による import 時間・起動時間の改善を**定量記録**する

### スコープ内
- registry 登録 116 件のうち R3-2/R3-3/R3-4 相当（`src/services` 系・`src/backend` 系・`src/models` 系・`src/api` 系）
- `test_shim_reference_gate.py` のスコープ拡張（config 限定 → 全 src）

### スコープ外（別計画）
- `src/llm/unified/` と `src/core/llm_gateway.py` の **adapters への統合**（これは shim 削除ではなく設計統合。Step 14 で持ち越し記録）
- 4層アーキテクチャへの大規模再配置（`docs/SERVICES_REORGANIZATION_PLAN.md` 系の別計画）

---

## 3. プリンシプル（PLAN_R3 からの継承 + 追加）

| # | プリンシプル | 根拠 |
|---|---|---|
| P1 | **参照解消コミットと削除コミットを必ず分離** | `fee262b1` インシデントの直接原因 |
| P2 | **1 コミット = 1 shim**（高トラフィック時は 1 shim でも 2 コミット: 置換 → 削除） | revert 粒度 |
| P3 | **ゲートは fail-closed・集合一致。** 旧パス参照の増加も減少も fail（ラチェット自走） | PLAN_R3 P3/P4 |
| P4 | **shadowing（同名衝突）は実行時解決で判定する。** regex の文字列一致を参照数と呼ばない | §1-4-1 の実測 |
| P5 | **削除した shim は復活検出リストに登録。** registry / REMOVED / ゲートベースラインを同一コミットで更新 | PLAN_R3 P5 |
| P6 | **DeprecationWarning は「抑制」ではなく「消す」。** pytest への `-W` 緩和をしない | §1-4-3 の教訓 |
| P7 | 完了条件はコマンドと期待結果。実行前 `git status` clean | PLAN_R3 P6/P7 |

---

## 4. ステップ詳細

### Phase A: 棚卸しと即時削除（Steps 1-3）

#### Step 1: shim 参照数マトリクスの再生成

- **成果物**: `scripts/scan_shim_usage.py`（新規）
- **設計**:
  - `config/shim_registry.json` の全エントリについて、PLAN_Q2 Step 2 の `verify_dead_code.py` と同じ 3 段階スキャン（AST strict / 文字列 loose / 動的参照）を実行
  - **shadowing 検出を追加**: 各 shim パスについて、同名ディレクトリ（`x.py` に対する `x/`）の存在と `importlib.util.find_spec` の解決先を比較し、**到達不能ファイル**を `shadowed` フラグで出力
  - 出力: `src 参照数 / tests 参照数 / shadowed / 削除可否` のマトリクス（Markdown テーブルを標準出力）
- **完了条件**:
  ```bash
  .venv/bin/python scripts/scan_shim_usage.py > var/shim_matrix_20261115.md   # 116 件全行が出力される
  ```
- **コミット**: `feat(q3): shim 参照数マトリクススキャナ（shadowing 検出つき）`

#### Step 2: 参照ゼロ + shadowed shim の即時削除（バッチ 1）

- **対象**: 実測 25 件（§1-3）+ **shadowed 3 件**（`src/agents/audit.py`、`src/agents/audit_agent.py`、`src/services/marketing.py` — Step 1 の再計測で確定した全件）
- **変更**: ファイル削除 + registry 除去 + `tests/regression/test_shim_removal_detection.py` の検出リスト追記（同一コミット）
- **注意**: shadowed ファイルの削除後も `find_spec` の解決先が変わらないこと（パッケージ側が解決され続ける）を完了条件で確認
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression -q --timeout=120     # 全緑（shim ゲート群を含む）
  .venv/bin/python -c "import src.agents.audit, src.services.marketing"   # パッケージ側の解決を確認（DeprecationWarning 減も確認）
  ```
- **コミット**: `refactor(q3): 参照ゼロ・shadowed shim を削除（バッチ1: 実測 28 件）`

#### Step 3: `test_shim_reference_gate.py` のスコープ拡張

- **対象**: `tests/regression/test_shim_reference_gate.py`（PLAN_R3 Step 4 で作成。現状 `config.*` 限定）
- **変更**:
  - スキャン対象モジュールを `config.*` から registry 登録全 shim（`src.services.*` / `src.backend.*` / `src.models.*` / `src.api.*` / `src.agents.*` / `src.core.*` / `src.engine.*` / `src.llm.*` / `src.domain.*`）へ拡大
  - ベースライン `config/shim_reference_baseline.json` に「各 shim の参照元ファイル集合」を記録（**集合一致**: 参照の増加も減少も fail。減少時は次コミットで baseline 引き下げ → 自走）
  - `(?<![\w.])` + `\b` の接頭辞/境界処理（`src.services.llm` vs `src.services.llm_service` の衝突防止）を PLAN_R3 Step 4 から踏襲
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_shim_reference_gate.py -q   # green（Step 2 後の状態で baseline 作成）
  ```
- **コミット**: `test(q3): shim 参照ゲートを全 src 対象に拡張（集合一致ベースライン）`

### Phase B: 高トラフィック shim（Steps 4-9）

#### Step 4: `src/backend/config.py` の参照解消（101 参照）

- **変更**: 57 src ファイル + tests の import を `src.infrastructure.config.settings` へ機械置換
  ```bash
  # 置換パターン（置換後は必ず目視 diff とテスト）
  grep -rl "from src.backend.config import" src tests | xargs sed -i \
    's/from src\.backend\.config import/from src.infrastructure.config.settings import/'
  grep -rl "src\.backend\.config\." src tests | xargs sed -i \
    's/src\.backend\.config\./src.infrastructure.config.settings./g'
  ```
- **注意**:
  - `from src.backend.config import X` の `X` が `Settings` / `settings` 以外（`__getattr__` 経由の再エクスポート名）の可能性 → 置換前に `python -c "import src.backend.config; print([n for n in dir(src.backend.config)])"` で全公開名を確認し、**公開名ごとに移設先を明示リスト化してから置換**
  - `import src.backend.config as cfg` 形式は手動修正
- **完了条件**:
  ```bash
  grep -rn "src\.backend\.config" src tests --include="*.py" | grep -v "infrastructure" | wc -l   # 0
  .venv/bin/python -m pytest tests/unit -q --timeout=120    # 全緑
  ```
- **コミット**: `refactor(q3): src.backend.config shim の参照を src.infrastructure.config.settings へ解消（57 ファイル）`

#### Step 5: `src/backend/config.py` の削除

- **変更**: ファイル削除 + registry 除去 + 復活検出リスト追記 + `docs/CONFIG_UNIFICATION_PLAN.md` の状態更新（同一コミット）
- **完了条件**:
  ```bash
  test ! -f src/backend/config.py
  .venv/bin/python -m pytest tests/regression -q --timeout=120   # shim ゲート群全緑
  ```
- **コミット**: `refactor(q3): src.backend/config.py shim を削除（registry 116 → 114）`

#### Step 6: `src/services/llm/*` の参照解消（47 参照）

- **対象**: `src/services/llm/__init__.py`（28）/ `factory.py`（12）/ `prompts.py`（4）/ 個別アダプタ
- **変更**: `from src.services.llm.factory import get_llm_adapter` → `from src.llm.adapters.factory import get_llm_adapter` 等へ置換。**移設先対応表を Step 1 のマトリクスから作り、コミットメッセージに添付**
- **注意**: `src.services.llm.retry` → `src.llm.adapters.retry` のように **ファイル名が変わっているペア**（`prompt_cache_builder` → `prompt_cache` 等）は sed 一発では行けない。対応表駆動の Python 置換スクリプトを一時使用し、**スクリプト自体はコミットしない**
- **完了条件**: `grep -rn "from src\.services\.llm" src tests --include="*.py" | wc -l` → 0、unit 全緑
- **コミット**: `refactor(q3): src.services.llm の参照を src.llm.adapters へ解消（28 ファイル）`

#### Step 7: `src/services/llm/*` の削除

- **変更**: shim 13 ファイル削除 + registry 除去 + 復活検出追記 + `docs/MOVEMENT_MAPPING.md` Phase 1 (Steps 7-14) の「未着手」を進行中に更新（同一コミット）
- **完了条件**: `test ! -d src/services/llm`、regression 全緑
- **コミット**: `refactor(q3): src/services/llm shim パッケージを削除（13 ファイル）`

#### Step 8: `database/core.py` + `llm/service.py` の参照解消（53 参照）

- **対象**: `src/backend/database/core.py`（14 / 35）、`src/llm/service.py`（13 / 18）
- **変更**: Step 4 と同じパターンで機械置換。`database/core.py` は `get_db` / `DatabaseManager` 等、公開名対応表を作ってから実施
- **完了条件**: 両モジュールの旧パス参照 0、unit 全緑
- **コミット**: `refactor(q3): database.core と llm.service の参照を新パスへ解消`

#### Step 9: 同 2 モジュールの削除

- **変更**: 削除 + registry 除去 + 復活検出追記
- **注意**: `src/backend/database/` パッケージ自体は現役（models / repositories が実コード）なので**`core.py` のみ削除**。`src/llm/service.py` は `src/llm/` 配下の単一ファイル削除
- **完了条件**: regression 全緑 + `find_spec` で新パス解決確認
- **コミット**: `refactor(q3): database.core / llm.service shim を削除（registry 116 → 96 相当）`

### Phase C: 中量級と二重定義統合（Steps 10-13）

#### Step 10: `src/models/db.py` の二重定義統合（逆転の是正）

- **対象**: `src/models/db.py`（`PlotDbModel` / `ChapterDbModel` 定義 + DeprecationWarning）と `src/domain/models/{plot,chapter}.py`
- **手順**:
  1. **等価性検証**: 両定義のカラム・制約・`__tablename__` を diff し、完全一致を確認（不一致なら**新パス側を実側に合わせる**方向で統一 — 本番が旧側で動いてきたため）
  2. 本番 5 ファイル（`src/core/interfaces.py:9`、`src/backend/engine_plot.py:18`、`src/agents/audit/logical_auditor.py:13` 等、Step 1 マトリクスで確定）を `src.domain.models.*` へ置換
  3. `src/models/db.py` 削除 + registry 除去 + 復活検出追記
  4. 既存回帰テスト `tests/regression/`（`src/domain/models` 側を参照している実測あり）の整合確認
- **完了条件**:
  ```bash
  grep -rn "from src\.models\.db\|src\.models\.db import" src tests --include="*.py" | wc -l   # 0
  .venv/bin/python -m pytest tests/unit tests/regression -q --timeout=120    # 全緑
  .venv/bin/python -c "import src.domain.models.plot"                        # warning なし
  ```
- **コミット**: `refactor(q3): PlotDbModel/ChapterDbModel を src.domain.models に統合し src/models/db.py を削除`

#### Step 11: 中量 shim のバッチ処理（book_score / logging_config / marketing 等）

- **対象**: `src/engine/book_score/{service,mapping}.py`（6+5 / 21+8）、`src/backend/logging_config.py`（4 / 6）、`src/services/marketing*`、Step 1 マトリクスの残り中量級（src 参照 ≤ 4）
- **変更**: PLAN_R3 の erotic_specialist 一括置換（同ファイルが複数 shim を参照するパターン）と同じく、**参照元ファイル単位で一括置換 → 1 カテゴリ 1 コミットで削除**
- **完了条件**: 対象カテゴリの旧パス参照 0、unit / regression 全緑
- **コミット**: `refactor(q3): 中量 shim をバッチ削除（book_score / logging_config / 他）`

#### Step 12: `src/api/*` と `src/backend/api/` の統合削除（第三の場所の解消）

- **対象**: `src/api/{health,dashboard,conflicts,agent_memory}.py`（router shim 4 件）+ `src/backend/api/admin_phase2.py`（shim、パッケージ内唯一のファイル）
- **設計**: 実体は `src/backend/routers/*` と `src/interfaces/api/*` にある。shim を削除し、**API の場所は 2 つに固定**（interfaces が app_factory / 追加 API、backend/routers が業務ルーター）。`src/api/middleware/` は実コード（error_handler.py）のため**削除せず現在地を SSOT として文書化**（4層統合は別計画）
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/security/test_server_route_mount_parity.py -q   # ルート一致性ゲートが緑（ルート数が変わらないこと）
  test ! -f src/backend/api/admin_phase2.py
  ```
- **コミット**: `refactor(q3): src/api と backend/api の router shim を削除し API 配置を 2 箇所に固定`

#### Step 13: DeprecationWarning ゼロゲートの新設

- **成果物**: `tests/regression/test_no_deprecation_warnings.py`（新規）
- **設計**:
  - `warnings.catch_warnings(record=True)` + `simplefilter("always")` の中で、`src` 配下の全 import 可能モジュールを `importlib.import_module`（または既存の import スキャン資産があれば流用）し、**`DeprecationWarning` が 1 件でも出たら fail**（出たモジュール名とメッセージを assert メッセージに含める）
  - 実行コスト対策: モジュール一覧は `git ls-files 'src/**/*.py'` から `__init__` / テスト専用物を除外して構築し、収集は 1 セッションで共有（pytest の session scope fixture）
  - `pytest.ini` の `filterwarnings` に**緩和設定を足さない**（P6）。逆に本ゲート導入後は `pytest.ini` に `filterwarnings = error::DeprecationWarning` を検討（Step 15 で判断）
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_no_deprecation_warnings.py -q   # green
  ```
- **コミット**: `test(q3): import 時 DeprecationWarning ゼロの常設ゲートを新設`

### Phase D: 完了判定・整備・定量記録（Steps 14-16）

#### Step 14: R4 判断と文書同期

- **内容**:
  1. `docs/SHIM_REMOVAL_PLAN.md` の R3-2/R3-3/R3-4 チェックリストを完了状態に更新。R4（registry 自体の削除）を**実施判断**として記録（残件ゼロなら registry を空 + `test_new_shims_registered.py` を「新規 shim 禁止」ゲートに転換する方針を明記）
  2. `docs/SHIM_PATTERN.md` を「新規 shim の作成は原則禁止。作る場合は registry 登録 + 削除期日の必須化」に改訂
  3. `docs/MOVEMENT_MAPPING.md` の Phase 1 状態を更新
  4. 持ち越し: `src/llm/unified/` + `src/core/llm_gateway.py` の adapters 統合（4 並列 LLM スタックの残り 2 本）を別計画として `plans/` に起票するか、本計画の「スコープ外」として明記
- **完了条件**: 上記 4 文書の更新が 1 コミットにまとまっている
- **コミット**: `docs(q3): SHIM_REMOVAL_PLAN の R3 完了記録と R4 判断、新規 shim 禁止方針へ改訂`

#### Step 15: import 時間ベンチマーク（定量記録）

- **コマンド**:
  ```bash
  # before は Step 4 開始前に取得済みであること（Step 3 のコミット時に記録）
  .venv/bin/python -X importtime -c "import src.backend.server" 2> /tmp/opencode/importtime_after.txt
  python3 - <<'EOF'
  # cumulative 上位 10 を集計して before/after を比較（scripts/ に恒久化してもよい）
  EOF
  ```
- **記録**: `docs/STATUS.md` または `CHANGELOG.md` に「shim 122 件削除による import 総時間の変化（実測 ms）」を記録。**122 モジュールの import 廃止は起動時間・テスト収集時間（実測 61.9 秒）の改善として効くはず**であり、その効果を数値で残す
- **完了条件**: before/after の数値が記録されている（改善しない場合もその実測を記録する — 目的は数値化であり美化ではない）
- **コミット**: `docs(q3): shim 削除による import 時間の before/after 実測を記録`

#### Step 16: 最終検証

- **コマンド**:
  ```bash
  git status --short                                            # clean
  make verify                                                    # 全緑
  .venv/bin/python -m pytest tests/unit tests/regression tests/security -q --timeout=120   # 全緑
  .venv/bin/python scripts/ci_lint_ratchet.py --tool all        # exit 0
  python3 -c "import json; print(len(json.load(open('config/shim_registry.json'))['shims']))"   # 残件数（目標: ≤ 10）
  grep -rn "DeprecationWarning" src --include="*.py" -l | wc -l  # 目標: 0（Step 13 のゲートが担保）
  ```
- **CI 確認**: 全ジョブ緑
- **コミット**: なし

---

## 5. 回帰テスト一覧（本計画で新設・拡張するもの）

| テスト / スクリプト | 種別 | 防ぐ再発 |
|---|---|---|
| `scripts/scan_shim_usage.py`（新規, Step 1） | 証明ツール | 文字列一致を「参照」と誤認する分析ミス。shadowing の見逃し |
| `tests/regression/test_shim_reference_gate.py` 拡張（Step 3） | 集合一致ゲート | 旧パス参照の再増加（shim を作り直す行為の抑止） |
| `tests/regression/test_shim_removal_detection.py` 更新（各削除コミット） | 復活検出 | 削除済み shim の再作成 |
| `tests/regression/test_no_deprecation_warnings.py`（新規, Step 13） | 常設ゲート | 「警告を出す実コード」の再出現（本計画の最重要ゲート） |
| `tests/security/test_server_route_mount_parity.py`（既存, Step 12 で活用） | ルート整合 | shim 削除によるルート喪失の検出 |

---

## 6. リスクとロールバック

| リスク | 対策 |
|---|---|
| 高トラフィック置換（57 ファイル / 28 ファイル）で公開名の取りこぼし | 置換前に shim の公開名一覧（`dir()` 実測）を作り、名前ごとに移設先を対応表化。置換後は unit 全実行 + `find_spec` 確認 |
| `src.services.llm.*` の名前変更ペア（`prompt_cache_builder` → `prompt_cache` 等）の機械置換ミス | sed 一発禁止。対応表駆動のスクリプトで置換し、unit 全実行 |
| `src/models/db.py` 統合時の等価性確認漏れ（カラム差・制約差） | Step 10 の手順 1 を必須化。不一致なら本番が動いてきた旧側に新パスを合わせる |
| router shim 削除でルートが消える | `test_server_route_mount_parity.py`（既存ゲート）を Step 12 の完了条件に明記 |
| DeprecationWarning ゲートの実行コストによる CI 遅延 | session scope で 1 回だけスキャン。重ければ `tests/regression` のみで実行し CI の別ジョブにする |
| ロールバック | 1 shim = 1〜2 コミット。`git revert` で shim 単位復帰。registry / 復活検出リストは同一コミット原則で自動的に戻る |

---

## 7. 完了の定義（Acceptance Criteria）

1. `config/shim_registry.json` の残件 ≤ 10（残るものは「理由 + 削除期日」付き。R4 判断が記録されている）
2. `grep -l DeprecationWarning src --include="*.py"` → 0 件、かつ常設ゲート `test_no_deprecation_warnings.py` が green
3. `make verify` / GitHub Actions 全ジョブ緑
4. import 時間の before/after 実測が記録されている
5. 旧パス参照（`src.backend.config` / `src.services.llm` / `src.models.db` / `src.api.*`）が src と tests で 0 件

---

## 8. 補遺：PLAN_Q4-R Step 22 実行記録（2026-11-17）

`src/llm/service.py` と `src/models/db.py` は PLAN_Q3 Step 9/10 で削除予定とされていたが、実際には本番 15 ファイル（`src/llm/service.py`）と 5 ファイル（`src/models/db.py` の `PlotDbModel`/`ChapterDbModel`）が参照中であることが判明（レビュー High 指摘）。

選択肢A（推奨・小）を採用：
- `src/models/db.py` の `PlotDbModel` を `src/domain/models/plot.py` に新規作成・移設
- `src/domain/models/chapter.py` に既存の `ChapterDbModel` あり（二重定義解消）
- 本番 5 ファイル（`src.core.interfaces`, `src.backend.engine_plot`, `src.models.writing`, `src.models.__init__`, `tests/unit/backend/test_backend_engine_facade_and_plot`）の import 先を `src.domain.models.*` に切り替え
- `src/llm/service.py` は「昇格完了・維持」として現存（14 ファイルが依存）

検証: mypy 対象ファイル 0 エラー、ruff 0 エラー、`tests/unit/backend/test_backend_engine_facade_and_plot.py` 33 passed、`tests/unit -k "plot or interface"` 387 passed
