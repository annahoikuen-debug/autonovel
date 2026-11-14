# PLAN_Q2: デッドコード削除 — 「削除から始める」 (13 STEPS)

> **目的**: 実 import がゼロ（または依存チェーンの中でだけ参照される）と**機械的に証明できる**モジュール群を、
> 再発防止ゲートを先に設置した上で削除する。目標 **src 約 -5,300 行**（実測値は §1-4）。
>
> **実測日**: 2026-11-15（参照数は `git ls-files` 全追跡 `.py` に対する AST/正規表現スキャンの実測）
> **前提**: `PLAN_Q1` が完了していること（unit suite が緑。ruff/mypy baseline が 0 / 実測値）。
> **後続**: `PLAN_Q3`（shim 焼却）。本計画で消す `src/core/llm_clients` 等は Q3 の対象リストからも減る。
> **作業方針**: PLAN_R3 のプリンシプル（P1 参照解消と削除の分離 / P2 1コミット1単位 / P3 ゲートは fail-closed）を継承。

---

## 1. 実測データ（2026-11-15 時点）

### 1-1. 削除候補と参照数（strict import スキャン実測）

| グループ | モジュール | src 参照 | tests 参照 | 行数 |
|---|---|---:|---:|---:|
| **G1: 完全無参照** | `src/generation/fallback_generator.py` | 0 | 0 | 97 |
| **G1: 完全無参照** | `src/services/pdca_cycle.py`（star-import shim） | 0 | 0 | 15 |
| **G2: test-only** | `src/logging/setup.py` | 0 | 1 | 35 |
| **G2: test-only** | `src/monitoring/otel.py` | 0 | 3 | 75 |
| **G2: test-only** | `src/monitoring/sentry.py` | 0 | 3 | 25 |
| **G2: test-only** | `src/generation/cache.py` | 0 | 1 | 176 |
| **G3: 旧8オーディター** | `src/agents/specialists/{consistency,style,factual,structure,creativity,emotion_curve,reader_hook,multimodal}_auditor.py` + `anti_ai_detector.py` | **1**（`specialists/__init__.py` の再エクスポートのみ） | モジュール別合計 40（重複込み、実行時に確定） | **1,906** |
| **G3: チェーン依存** | `src/agents/specialists/fallback_utils.py` | **4**（すべて旧オーディターから） | 1 | **993** |
| **G3: 本番の唯一の参照** | `src/backend/routers/admin_phase2.py`（`/admin/audit/aggregate_test` デバッグエンドポイントが `llm=None` で旧8オーディターを生成） | — | integration 1 ファイル | — |
| **G4: LLM 死体チェーン** | `src/llm/clients/{gemini,openai}.py` | 相互参照のみ（`src/core/llm/__init__.py`・`src/core/llm_clients/__init__.py`・providers） | 4 ファイル | 645 |
| **G4: LLM 死体チェーン** | `src/llm/{gemini_provider,openai_provider}.py` | 相互参照のみ | 0 | 244 |
| **G4: LLM 死体チェーン** | `src/core/llm/__init__.py` / `src/core/llm_clients/__init__.py`（shim） | Q4 の G4 からの参照のみ | — | 225 |
| **G5: Python ツリー内 TS** | `src/components/editor/*.tsx`（4 ファイル）+ `src/hooks/useInlineRevision.ts` | Python からの import 0。**frontend 側の同一ファイルと乖離した stale フォーク**（`diff` 実測で相違あり） | 0 | **883** |
| 合計（src） | | | | **約 5,319 行** |

### 1-2. 削除禁止リスト（誤って削らないための明示）

| モジュール | 理由（実測） |
|---|---|
| `src/generation/pdca_controller.py` | **使用中**。`src/domain/writing/coordinator.py:14,62` が PDCA 再生成判断に使用。`src/agents/audit_agent/agent.py:134` も使用 |
| `src/engine/pdca_cycle.py`（`ClosedLoopPDCARunner`） | `src/services/commercial_benchmarks.py:171` と unit/integration 計 6 テストが参照。**パイプラインへの配線（実行経路）は無い**が、削除ではなく「配線するか」の設計判断の対象（Step 12 で持ち越し記録） |
| `src/llm/unified/` | `src/agents/specialist_auditor_base.py`・`src/agents/writing/agent.py` が参照（4 ファイル）。削除ではなく Q3 以降の「adapters への統合」対象 |
| `src/services/pdca_directive.py` | `src/engine/pdca_cycle.py:18` が参照（`ClosedLoopPDCARunner` を温存する限り削除不可） |

> **訂正**: `docs/STATUS.md` §3-6 は「`ClosedLoopPDCARunner` はどこからも import されていない」と記載するが、
> 実測では `commercial_benchmarks.py` とテスト群が import している（**実行経路は無い**が import はある）。
> Step 12 で STATUS.md を実態に合わせて修正する。

### 1-3. 削除の外側で同時に起こること

- `src/llm/clients/test_api_clients.py` の失敗 1 件（PLAN_Q1 分類 C）は **G4 削除と同時に消える** → Q1 Step 14 の既知の赤予算を 0 に引き下げる
- 旧8オーディターの test ファイル（モジュール別合計 40・重複込み）は「UnifiedAuditor を叩く等価テスト」が既に存在する（`tests/audit/test_unified_*`）ため、**移行ではなく削除が基本**。ただし各ファイルで `UnifiedAuditor` への置換で保存すべき観点がないか 30 秒チェックする（P4）

---

## 2. 目的・スコープ

### 目的
1. 参照ゼロを**機械証明**した上で、5 グループのデッドコードを削除する（src 約 -5,300 行）
2. 削除済みモジュールの**復活を検出するゲート**（`test_dead_code_stays_dead.py`）を先に設置する
3. 削除に伴う tests / registry / ドキュメントを同一コミットで同期する

### スコープ内
- §1-1 の G1〜G5、対応する tests、`config/shim_registry.json` の該当エントリ、admin_phase2 のレガシーエンドポイント
### スコープ外
- `src/llm/unified` の統合（Q3 以降）、`src/services/` の shim 削除全般（Q3）、PDCA の配線設計判断（Step 12 で持ち越し）

---

## 3. プリンシプル

| # | プリンシプル | 根拠 |
|---|---|---|
| P1 | **ゲート先置き。** 削除検出テストを削除より先に導入し、以降の全コミットで green を保つ | PLAN_R3 のインシデント（`fee262b1`）の教訓: 削除は「壊れた状態で発見」されがち |
| P2 | **1 コミット = 1 グループ（または 1 モジュール）。** 参照解消コミットと削除コミットは分離 | PLAN_R3 P1/P2 を継承 |
| P3 | **参照ゼロの証明は AST strict + 文字列 loose + 動的参照（importlib / `__import__` / setattr 文字列）の 3 段階**。スキャン対象は `git ls-files` 全追跡 `.py`（ルート手動列挙禁止） | PLAN_R3 §0 の発見事項（3 ディレクトリの走査漏れ）を構造的に再発防止 |
| P4 | **テストは「消す」前に「観点の価値」を 30 秒確認。** UnifiedAuditor が同観点をカバーしているか確認してから消す | 旧8オーディターの perturbation 等の資産を誤廃棄しない |
| P5 | **frontend 側にだけ存在する差分は削除前に手動確認。** `src/components/editor/*.tsx` は frontend のフォークであり、`frontend/src` 側に無い変更があれば取り込むか明示的に放棄する | stale フォークの `diff` 実測で相違あり |
| P6 | 完了条件はコマンドと期待結果。実行前 `git status` clean 確認 | PLAN_R3 P6/P7 を継承 |

---

## 4. ステップ詳細

### Phase A: 安全網の構築（Steps 1-3）

#### Step 1: 削除候補インベントリの確定と削除禁止リストの明示

- **内容**: 本計画 §1-1 / §1-2 をインベントリとして確定。**削除禁止リスト（§1-2）を `config/protected_modules.json` に機械可読で登録**（将来の自動スキャンが「削除候補」として誤検出しないためのホワイトリスト）
- **完了条件**: `python3 -c "import json; print(len(json.load(open('config/protected_modules.json'))['protected']))"` → 4 以上
- **コミット**: `chore(q2): デッドコード削除インベントリ確定 + 削除禁止モジュールの機械可読登録`

#### Step 2: 参照ゼロ証明スクリプト `scripts/verify_dead_code.py` 新設

- **設計**（P3 を実装）:
  - 入力: 削除候補モジュールのパス一覧（`--list config/removed_modules.json`）
  - 段階 1 (strict): `ast` で `ast.Import` / `ast.ImportFrom` を走査。`from src.llm.clients import …` / `import src.llm.clients` を検出。**接頭辞衝突の排除**（`src.llm.clients_extra` が `src.llm.clients` に誤一致しないよう `(?<![\w.])` + `\b` を必須化 — PLAN_R3 Step 4 の教訓）
  - 段階 2 (loose): ファイル全体の文字列にモジュールパス（`src/llm/clients`、`src.llm.clients`）が含まれる検出（docstring / `importlib.import_module("…")` / `monkeypatch.setattr("…")` を拾う）
  - 段階 3 (dynamic): `importlib` / `__import__` / `getattr(…, "文字列")` / `import_module` の呼び出しを全抽出し、引数文字列が候補に一致するか照合
  - 出力: モジュールごとの `strict / loose / dynamic` 参照一覧と、`tests/` / `src/` 別集計。**strict または dynamic に参照があれば exit 1**
  - スキャン対象: `git ls-files -z -- '*.py'`（+ `.ts`/`.tsx` は G5 用に `--include-web` フラグ）。git 未検出環境では `pytest.skip` 相当（PLAN_R3 Step 4 と同じ方針）
- **完了条件**:
  ```bash
  .venv/bin/python scripts/verify_dead_code.py --check   # 削除候補全件が src 参照 0（G3/G4 は「グループ内相互参照のみ」）で exit 0
  ```
- **コミット**: `feat(q2): 参照ゼロ証明スクリプト verify_dead_code.py（AST/文字列/動的参照の 3 段階）`

#### Step 3: 復活検出ゲート `tests/regression/test_dead_code_stays_dead.py` 新設

- **設計**:
  - `config/removed_modules.json` に「削除済みモジュールのパス一覧」をベースラインとして保持（PLAN_R3 の `test_shim_removal_detection.py` と同じ集合一致方式: **増加も減少も fail** — 復活も、勝手な追加も検出）
  - 検証内容: (a) 各パスが `git ls-files` に存在しないこと、(b) `sys.modules` / import で復活しないこと（`importlib.util.find_spec` が None）、(c) コードベース全体に旧パスの import 文が無いこと（Step 2 のスクリプトをライブラリ呼び出し）
- **完了条件**:
  ```bash
  .venv/bin/python -m pytest tests/regression/test_dead_code_stays_dead.py -q   # green（現時点では空ベースライン + G1〜G5 は未削除なので、ベースラインは削除コミットごとに追記する運用を docstring に明記）
  ```
- **コミット**: `test(q2): 削除済みモジュール復活検出ゲート（集合一致ベースライン）`

### Phase B: 無参照デッドコード（G1/G2 / Steps 4-5）

#### Step 4: G1 完全無参照の削除

- **対象**: `src/generation/fallback_generator.py`、`src/services/pdca_cycle.py`
- **変更**: ファイル削除 + `config/removed_modules.json` 追記 + `config/shim_registry.json` から `src/services/pdca_cycle.py` のエントリ除去（同一コミット、P5 相当）
- **注意**: `src/services/pdca_cycle.py` は `from src.engine.pdca_cycle import *` の star-import shim。**実体 `src/engine/pdca_cycle.py` は削らない**（§1-2）
- **完了条件**:
  ```bash
  .venv/bin/python scripts/verify_dead_code.py --check                          # exit 0
  .venv/bin/python -m pytest tests/regression/test_dead_code_stays_dead.py -q   # green
  .venv/bin/python -m pytest tests/unit -q --timeout=120                        # 新規失敗 0
  ```
- **コミット**: `refactor(q2): 完全無参照モジュールを削除（fallback_generator / services.pdca_cycle shim）`

#### Step 5: G2 test-only モジュールの削除

- **対象**: `src/logging/setup.py`、`src/monitoring/otel.py`、`src/monitoring/sentry.py`、`src/generation/cache.py` + 対応 tests（実測 6 ファイル: `tests/logging/test_setup.py`、`tests/monitoring/{test_otel,test_sentry,test_observability}.py`、`tests/infrastructure/test_monitoring_init.py`、`tests/generation/test_cache_lru.py`）
- **事前確認**:
  - `pyproject.toml` の `observability` extra（sentry-sdk）と `src/api/middleware/error_handler.py` の try/except import 保護は**実コード側に残る**（monitoring パッケージ自体は削除しない。`src/monitoring/` 配下の test-only 2 ファイルのみ）
  - `src/logging/setup.py` は `pyproject.toml` の依存コメントに「`src/logging/setup.py:2 が無条件に import するため loguru 必須」とある → **該当コメントの指す実体を `src/infrastructure/logging_config.py` に修正**（コメントと実態の乖離を解消）
- **変更**: ファイル削除 + 対応 tests 削除 + `removed_modules.json` 追記 + pyproject コメント修正（同一コミット）
- **完了条件**: Step 4 と同じ 3 コマンド + `grep -rn "from src.logging.setup\|from src.monitoring" src tests --include="*.py"` → 0 件
- **コミット**: `refactor(q2): test-only モジュールを削除（logging.setup / monitoring.otel / monitoring.sentry / generation.cache）`

### Phase C: 依存チェーンの削除（G3/G4/G5 / Steps 6-9）

#### Step 6: 旧8オーディターの参照解消（削除前の R2 相当）

- **対象**:
  1. `src/agents/specialists/__init__.py`: 旧8オーディターの再エクスポートと `DeprecationWarning` を削除（`adapter.py` 等の**現行クラスの再エクスポートは温存**）
  2. `src/backend/routers/admin_phase2.py`: `/admin/audit/aggregate_test` エンドポイントを削除（旧8オーディターを `llm=None` で並べるだけのデバッグ用。本番監査は UnifiedAuditor に一本化済み）。`SpecialistInfo` / `AuditAggregateTest*` の pydantic モデルも同時に削除。`/specialists`・`/weights` エンドポイントは維持
  3. `tests/integration/test_observability_and_admin_api.py::test_admin_audit_aggregate_test`: エンドポイント削除に合わせ削除
  4. frontend 側に `/aggregate_test` 呼び出しが無いことを確認（実測: `grep aggregate_test frontend/src` → 0 件。PDCALiveMonitor の `specialists` は別 payload の表示なので影響なし）
- **完了条件**:
  ```bash
  .venv/bin/python scripts/verify_dead_code.py --check   # G3 の strict 参照が「テストのみ」になる
  .venv/bin/python -m pytest tests/unit/backend tests/integration/test_observability_and_admin_api.py -q --timeout=120   # green
  ```
- **コミット**: `refactor(q2): 旧8オーディターの参照解消（specialists __init__ と aggregate_test エンドポイント）`

#### Step 7: 旧8オーディター + `fallback_utils` の削除（G3）

- **対象**: 9 ファイル（1,906 行）+ `src/agents/specialists/fallback_utils.py`（993 行、**旧オーディターからのみ参照される**ためチェーン削除）+ 対応 tests（モジュール別実測合計 40 ファイル・重複込み。P4 の 30 秒チェックを各ファイルで実施し、保存価値のある観点は `tests/audit/` の UnifiedAuditor 系にコメント付きで証拠移植）
- **変更**: 削除 + `removed_modules.json` 追記 + `docs/architecture.md` の「8 専門オーディタークラスは後方互換のため維持」という記述を実態に合わせ更新
- **完了条件**:
  ```bash
  .venv/bin/python scripts/verify_dead_code.py --check
  .venv/bin/python -m pytest tests/audit tests/unit -q --timeout=120    # green（audit 系は UnifiedAuditor 系テストが残る）
  wc -l src/agents/specialists/*.py | tail -1                            # 削減行数を記録
  ```
- **コミット**: `refactor(q2): 旧8オーディターと fallback_utils を削除（-2,899 行、UnifiedAuditor に一本化）`

#### Step 8: LLM 死体チェーンの削除（G4）

- **対象**: `src/llm/clients/`（2 ファイル 645 行）、`src/llm/gemini_provider.py`、`src/llm/openai_provider.py`（244 行）、`src/core/llm/__init__.py`、`src/core/llm_clients/__init__.py`（shim、225 行）+ 対応 tests（`tests/unit/llm/clients/` 4 ファイル等）
- **注意**:
  - `src/core/llm/` 配下に `adapters/`（現行）が同居しているため、**`src/core/llm/` パッケージ自体は削除しない**。参照ゼロの `__init__.py` の star re-export と `src/core/llm_clients/` パッケージのみ削除
  - `src/core/llm/__init__.py` の削除後、`src/core/llm/adapters/` への import が壊れないことを必ず確認（`src.core.llm.adapters` は `src.core.llm` パッケージの存在に依存するため、`__init__.py` は空ファイルとして維持するのが安全）
  - 本 Step で **PLAN_Q1 分類 C の赤 1 件が消える** → Q1 で作った既知の赤予算（Step 9 登録分）を 0 に更新
- **完了条件**:
  ```bash
  .venv/bin/python -c "import src.core.llm.adapters"                     # 現行経路の生存確認
  .venv/bin/python scripts/verify_dead_code.py --check
  .venv/bin/python -m pytest tests/unit -q --timeout=120                 # failed 0（Q1 分類C 解消）
  ```
- **コミット**: `refactor(q2): デッド LLM クライアント/providers/shim を削除（-1,114 行）`

#### Step 9: Python ツリー内 TS の削除（G5）

- **対象**: `src/components/editor/{Editor,DiffViewer,InlineAiToolbar,InlineRevisionDiffModal}.tsx`、`src/hooks/useInlineRevision.ts`（883 行）
- **事前確認（P5）**:
  1. `diff src/components/editor/Editor.tsx frontend/src/components/editor/Editor.tsx` の差分を一覧化
  2. 差分のうち **frontend 側に存在しない変更**がある場合、その価値を判断（取り込むか、明示的に放棄するか）。実測では frontend 側が先行改修されており、フォーク側は追従していない
  3. `src/hooks/useInlineRevision.ts` は frontend 側に対応物が**無い**（実測）→ frontend に必要か確認し、不要なら削除、必要なら frontend へ移設
- **変更**: 削除 + `pyproject.toml` の `[tool.setuptools] include` から frontend 混入の可能性がないか確認（現状 include は `src` だが、wheel に `.tsx` が含まれていないことを `python -m build` の代わりに `git ls-files src/components` で確認）+ ドキュメント（`docs/MOVEMENT_MAPPING.md`）に「React コードは frontend/src が SSOT」と明記
- **完了条件**:
  ```bash
  ls src/components src/hooks 2>&1 | grep -c "No such"    # 2（両方存在しない）
  .venv/bin/python -m pytest tests/regression -q --timeout=120   # green
  ```
- **コミット**: `refactor(q2): Python ツリー内の stale な React フォークを削除（-883 行、frontend が SSOT）`

### Phase D: 検証・記録・持ち越し（Steps 10-13）

#### Step 10: 全回帰と削減計測

- **コマンド**:
  ```bash
  git diff $(git rev-parse HEAD)~N --stat | tail -3     # N = 本計画のコミット数。削減行数を記録
  .venv/bin/python -m pytest tests/unit -q --timeout=120          # failed 0
  .venv/bin/python -m pytest tests/regression -q --timeout=120    # 全緑
  .venv/bin/python -m pytest tests/audit -q --timeout=120         # UnifiedAuditor 系が全緑
  .venv/bin/python -m ruff check src tests config scripts         # 0 維持（削除で誤検出が減る方向のみ）
  .venv/bin/python -m mypy src | tail -1                          # 件数が減っていること（baseline 更新は Step 11）
  ```
- **完了条件**: src 削減 **≥ 5,000 行**、unit / regression / audit 全緑
- **コミット**: なし（検証のみ）

#### Step 11: baseline / registry / CHANGELOG の同期

- **内容**:
  1. `config/ci_lint_baseline.json`: mypy 減少分をローカル `--update` で確定（P5: CI 自動引き下げは消失する）。`history` に本計画の削除による減少を記録
  2. `config/shim_registry.json`: 削除した shim エントリ（`services/pdca_cycle.py` 等）の除去を確認
  3. `CHANGELOG.md`: `[Unreleased]` に「デッドコード削除（src 約 -5,3XX 行）: 旧8オーディター・デッド LLM クライアント・Python ツリー内 React フォーク等」と記載。破壊的変更（`/admin/audit/aggregate_test` 削除）を明記
- **完了条件**: `python3 scripts/ci_lint_ratchet.py --tool all` → exit 0、`grep -A3 "Unreleased" CHANGELOG.md` に記載あり
- **コミット**: `chore(q2): baseline / registry / CHANGELOG をデッドコード削除の実態に同期`

#### Step 12: STATUS.md の訂正と設計判断の持ち越し記録

- **内容**:
  1. `docs/STATUS.md` §3-6 を実態に訂正: 「`ClosedLoopPDCARunner` は import こそ存在する（commercial_benchmarks・テスト）が、**生成パイプラインの実行経路には配線されていない**」に修正
  2. `docs/STATUS.md` §2 に PDCA 配線の設計判断を**持ち越し事項**として明記（自動改善ループの実装判断 = `plans/` の別計画で扱う）
  3. `docs/STATUS.md` §3-3 のなろう selenium 記載等、他の既知制限は触らない（Q2 の範囲外）
- **完了条件**: `grep -n "ClosedLoopPDCARunner" docs/STATUS.md` が実態どおりの記述になっている
- **コミット**: `docs(q2): STATUS の PDCA 記載を実態に訂正し、配線判断を持ち越し事項として明記`

#### Step 13: 最終検証

- **コマンド**:
  ```bash
  git status --short                          # clean
  make verify                                  # 全緑
  .venv/bin/python scripts/ci_lint_ratchet.py --tool all   # exit 0
  ```
- **CI 確認**: push 後の全ジョブ緑を確認
- **コミット**: なし

---

## 5. 回帰テスト一覧（本計画で新設するもの）

| テスト / スクリプト | 種別 | 防ぐ再発 |
|---|---|---|
| `scripts/verify_dead_code.py`（新規, Step 2） | 証明ツール | 「参照ゼロのつもり」だった削除が本番 import を壊す事故（PLAN_R3 の `fee262b1` と同型） |
| `tests/regression/test_dead_code_stays_dead.py`（新規, Step 3） | 復活検出 | 削除済みモジュールの再出現・再作成。**集合一致**なので、勝手なベースライン緩和も検出 |
| `config/protected_modules.json`（新規, Step 1） | ホワイトリスト | 使用中モジュール（pdca_controller 等）を将来の自動削除ツールが誤って候補に挙げる事故 |
| Step 6-8 各コミットの unit / audit 全実行 | 行動規律 | 削除コミットでの赤混入（Q1 P2 の規律を Q2 でも強制） |

---

## 6. リスクとロールバック

| リスク | 対策 |
|---|---|
| 旧8オーディターのテストに、UnifiedAuditor がカバーしない独自観点があった場合の品質劣化 | P4 の 30 秒チェックを全対象テスト（モジュール別合計 40・重複込み）で実施。証拠移植（観点名とテスト意図のコメント）を残す。perturbation 系テスト（`tests/audit/perturbation/`）は **transforms 系で現役**のため削除対象外であることを Step 7 で再確認 |
| `src/core/llm/__init__.py` 削除で `src.core.llm.adapters` が壊れる | Step 8 の完了条件に import 生存確認を明記。壊れる場合は空 `__init__.py` を残す |
| `aggregate_test` エンドポイントに外部依存があった場合 | 実測で frontend 呼び出し 0 件。integration 1 テストのみ同時削除 |
| G5 の frontend 差分に重要な修正が隠れていた場合 | P5 の diff 一覧化を Step 9 の最初に実施し、判断をコミットメッセージに記録 |
| ロールバック | 1 Step = 1 コミット。`git revert` でグループ単位で復帰。`removed_modules.json` も同 revert で戻る（同一コミット原則） |

---

## 7. 完了の定義（Acceptance Criteria）

1. `scripts/verify_dead_code.py --check` → exit 0（G1〜G5 が存在しない）
2. `pytest tests/unit tests/regression tests/audit -q` → 全緑、xpassed 0
3. src 削減 ≥ 5,000 行（`git diff --stat` の実測を CHANGELOG に記録）
4. `make verify` / GitHub Actions 全ジョブ緑
5. `docs/STATUS.md` の PDCA 記載が実態と一致している
