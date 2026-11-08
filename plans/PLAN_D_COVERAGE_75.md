# PLAN_D: カバレッジ閾値 60→75% 引き上げと carve-out 治理（詳細実装計画書）

- 作成日: 2026-11-08
- 対象ブランチ: `feature/commercial-lp-phase1`
- 根拠: プロジェクト厳格評価（総合 C+）の改善提案 **項目4**
- 実測条件: CI と同一コマンド（§8）／`.venv`（coverage 7.17.0 / pytest-cov 7.1.0）
- 関連: `docs/TEST_STRATEGY.md`（「カバレッジ閾値の漸進的向上 55% → 65% → 75%」と宣言済み）、
  `docs/SHIM_REMOVAL_PLAN.md`、`tests/regression/test_lint_budget.py`（予算固定型の雛形）

---

## 0. 目的と非目標

### 目的（3つ）

1. **閾値を 60 → 75 に引き上げる**（§1.1 の実測では既に 78.11% なので設定変更で到達可能。§2 で詳述）。
2. **閾値と実測の乖離を 18.11pt → 1pt 台に詰める**（＝「大幅な回帰でも通過してしまう」状態の解消）。
3. **除外（carve-out）を仕様として固定し、恣意的な除外追加を機械的に検出する**。

### 非目標

| 非目標 | 理由 |
|---|---|
| 統合テスト 9 件のゲート化 | 評価の改善優先 1 位。別計画。測定スコープとは分離する（§7.3） |
| mypy 1,122 件の引き下げ | 別項目。混ぜない |
| フロントエンド `thresholds: 50` の引き上げ | 別バイナリ。本計画の「75%」はバックエンド `src/` のみ |
| カバレッジ 80% / 90% への引き上げ | 本計画は「75 を守れる状態」まで。80+ は §9 の将来項として記載 |
| テスト実行時間の短縮 | coverage 付与は遅くなるが、速度は成功基準に含めない |

---

## 1. 現状実測（2026-11-08 / CI と同一コマンド）

### 1.1 総括 — **現状 78.11%（閾値 60 を 18.11pt 上回っている）**

| 指標 | 値 |
|---|---|
| **総カバレッジ（`coverage report` TOTAL / `fail_under` が比較する値）** | **78.11%** |
| 行カバレッジのみ（line-only） | 80.92%（covered 54,275 / statements 67,076） |
| 分岐カバレッジのみ（branch-only） | **67.73%**（covered 12,294 / branches 18,152） |
| 分母（fail_under の比較単位） | **85,228 単位** = statements 67,076 + branches 18,152 |
| 分子（カバー済み単位） | 66,569 単位 |
| 未カバー（missing lines / missing branches） | 12,801 行 / 5,858 分岐 |
| 除外済み（`exclude_lines` により分母から外れた行） | 276 行 |
| 測定ファイル数 | 1,077 |
| 実行結果 | 20 failed / 9,502 passed / 52 skipped / 407 deselected（16 分 44 秒） |

> **`branch = true` が有効**なため、`fail_under` の比較値は「行 + 分岐」を合算した 78.11% である。
> 行だけで見れば 80.92% だが、**分岐だけを見ると 67.73%** という大きな開きがある（§2 問題2）。

### 1.2 測定スコープの不一致（先に直すべき既存の矛盾）

カバレッジを測る入口が **3 系統**あり、値が一致しない。閾値を上げる前に統一しないと
「ローカルで 78% / CI で 62%」という検証不能な状態になる。

| # | 入口 | コマンド | 測定対象 | 閾値 |
|---|---|---|---|---|
| A | CI `test` ジョブ (`.github/workflows/ci.yml:126`) | `pytest -q -m "not integration and not perf and not slow" --cov=src --cov-fail-under=60 --timeout=120` | 非統合・非性能・非遅延 | 60 |
| B | `make test-unit` (`Makefile:62`) | `pytest tests/unit ... --cov-fail-under=60` | **`tests/unit` のみ**（regression / contract / security / e2e を含まない） | 60 |
| C | `make coverage` / `scripts/measure_coverage.py` | `pytest --cov=src ...`（`-m` フィルタ**なし**） | 全テスト（integration 含む。Docker 無しでは失敗） | なし |

**本計画の実測は A と同一コマンド**（§8）。

B の問題: 「対象が狭いのに同じ閾値 60」なので、A を満たすためのテストが `tests/unit` に
偏る誘因になる。C の問題: Docker 無しで再現できない。

### 1.3 スコープの不安定性：マーカーの付与漏れ

`-m "not integration and not perf and not slow"` はマーカーに依存するが、**付与が一貫していない**。

- `tests/perf/` の 7 ファイルのうち `@pytest.mark.perf` が付いているのは
  `test_performance_regression.py` / `test_vector_store_perf.py` のみ。
  `test_v6_llm_call_budget.py` 等は**未付与のまま実行・測定されている**。
- `tests/performance/` も同様（`test_fusion_perf.py` は未付与で実行された）。
- `tests/e2e/`（17 ファイル）・`tests/security/`（12 ファイル）はマーカーなし＝常に測定対象。

→ **測定スコープが「マーカーの付与漏れ」に左右される**。閾値を引き上げると、
マーカーを 1 つ付けるだけでカバレッジが変わり、ゲートが誤作動し得る。
Step 0 でスコープを固定し、Step 4 でマーカーの整合を検査する。

### 1.4 閾値の所在（5 箇所）

| 場所 | 現値 | 備考 |
|---|---|---|
| `pyproject.toml` `[tool.coverage.report].fail_under` | 60 | **pytest-cov が読む本体** |
| `.github/workflows/ci.yml:126` `--cov-fail-under=60` | 60 | 明示指定＝pyproject を上書き |
| `Makefile:62` `--cov-fail-under=60` | 60 | `make test-unit`（`tests/unit` 専用） |
| `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md:84` | 60 | 記述のみ |
| `tests/config/test_phase1_coverage.py` | `>= 55` | **既存の下限テストだが 55 しか見ていない**（60 への引き上げを検知できない） |

### 1.5 パッケージ別（branch 含む／`fail_under` と同じ指標）

| パッケージ | branch% | line% | statements | branches | missing 単位 |
|---|---:|---:|---:|---:|---:|
| **nsfw** | **34.82** | 43.51 | 262 | 74 | 219 |
| **monitoring** | **45.16** | 54.00 | 50 | 12 | 34 |
| **presets** | **52.81** | 53.52 | 71 | 18 | 42 |
| **interfaces** | **61.46** | 65.58 | 398 | 82 | 185 |
| **backend** | **65.62** | 68.87 | 14,379 | 3,578 | **6,174** |
| **pipeline** | **69.73** | 75.62 | 726 | 232 | 290 |
| **infrastructure** | **70.10** | 73.41 | 3,603 | 528 | 1,235 |
| **application** | **70.79** | 75.09 | 1,445 | 154 | 467 |
| agents | 76.26 | 79.29 | 9,839 | 3,382 | 3,139 |
| config | 76.94 | 81.74 | 619 | 140 | 175 |
| llm | 77.59 | 80.65 | 1,819 | 586 | 539 |
| core | 78.41 | 83.17 | 1,230 | 266 | 323 |
| services | 78.57 | 80.77 | 3,807 | 930 | 1,015 |
| cli | 79.05 | 78.33 | 240 | 56 | 62 |
| audit | 81.11 | 82.82 | 227 | 80 | 58 |
| integrations | 81.11 | 83.68 | 3,701 | 1,116 | 910 |
| fusion | 82.73 | 86.15 | 462 | 146 | 105 |
| stores | 84.21 | 85.86 | 481 | 146 | 99 |
| models | 84.26 | 89.97 | 2,831 | 480 | 521 |
| engine | 85.68 | 87.87 | 7,327 | 2,600 | 1,422 |
| shared | 85.81 | 89.54 | 239 | 50 | 41 |
| annotations | 86.12 | 89.83 | 344 | 146 | 68 |
| domain | 86.95 | 89.39 | 4,422 | 990 | 706 |
| narrative | 88.25 | 90.47 | 1,112 | 360 | 133 |
| generation | 88.64 | 90.80 | 174 | 46 | 25 |
| src（直下） | 89.47 | 94.12 | 17 | 2 | 2 |
| rules | 91.35 | 92.72 | 481 | 120 | 52 |
| utils | 92.11 | 95.83 | 72 | 4 | 6 |
| narrative_balancer | 92.13 | 94.41 | 1,718 | 454 | 171 |
| publishing | 92.31 | 93.40 | 2,968 | 712 | 283 |
| security | 94.12 | 100.00 | 15 | 2 | 1 |
| easy_mode | 95.29 | 96.47 | 1,784 | 636 | 114 |
| api | 96.47 | 97.18 | 71 | 14 | 3 |
| logging | 100.00 | 100.00 | 7 | 0 | 0 |
| plugins | 100.00 | 100.00 | 135 | 10 | 0 |

**missing 単位の大きい順（改善レバレッジ）**:
`backend` 6,174（全体に +7.24pt の余地）／`agents` 3,139（+3.68pt）／
`engine` 1,422（+1.67pt）／`infrastructure` 1,235（+1.45pt）／
`services` 1,015（+1.19pt）／`integrations` 910（+1.07pt）。

### 1.6 分母から隠れているもの（omit の規模）

| omit 対象 | ファイル数 | statements |
|---|---:|---:|
| `src/**/__init__.py`（4 階層パターン） | 141 | **1,377** |
| `src/**/migrations|alembic/**` | 30 | **954** |
| 明示 3 ファイル（`age_client.py` / `core/exceptions.py` / `services/marketing.py`） | 3 | 11 |
| **合計** | **174** | **2,342** |

`src/` 全体の statements は 70,218、測定対象は 67,076。
→ **omit により 3.4% の statements が分母に存在しない**（`exclude_lines` はさらに 276 行を除外）。

---

## 2. ギャップ算定 — 「75% に届かない」のではなく「75% が意味を持たない」

### 2.1 数字の整理

```
分母（単位） = 67,076 statements + 18,152 branches = 85,228
分子（カバー済み） = 66,569
現状 = 66,569 / 85,228 = 78.11%

75% の必要量 = 0.75 × 85,228 = 63,921 単位  → 現状は +2,648 単位の余裕
60% の必要量 = 0.60 × 85,228 = 51,137 単位  → 現状は +15,432 単位の余裕
```

| 課題 | 計算 | 含意 |
|---|---|---|
| **問題1: 閾値と実測の乖離 18.11pt** | 60% 閾値を割るには **15,432 単位**（＝現状の 23%）が蒸発してもよい | カバレッジの**半分近くを失っても CI は緑**。回帰検出力がほぼ無い |
| **問題2: 分岐カバレッジ 67.73%** | 分岐 18,152 のうち 5,858 が未到達。行 80.92% と **13.19pt の開き** | 「行は通るが分岐が死んでいる」＝異常系・エラー経路が未検証 |
| **問題3: 下位パッケージが総合値に隠れる** | nsfw 34.82% / monitoring 45.16% / presets 52.81% / interfaces 61.46% / **backend 65.62%** | 総合 78.11% でも **backend（14,379 statements＝全体の 21%）は 65.62%** |
| **問題4: carve-out が未仕様** | stale 1 件（`src/schemas/easy_mode.py` はファイル不在）、台帳なし、pragma 27 箇所に理由なし | 除外の追加・削除が誰のレビューも通らずに行える |

### 2.2 したがって本計画の姿勢

> **「75% に到達する」は Step 1 の設定変更 1 行で終わる。本計画の本体は
> (a) 75 を*守れる*密度に閾値を詰める、(b) 除外を仕様化する、(c) 総合値に隠れた弱い内訳を
> フロアで表に出す、の 3 点である。**

これを隠さず明記するのは、「60→75 に 40 ファイル分のテストを書く」という計画は
**実測と矛盾する空想**だからである。実測に基づいて、必要な作業だけを計画する。

---

## 3. carve-out の現状棚卸しと仕様

### 3.1 分類 — 除外手段は 3 種類のみ（この 3 種類以外は禁止）

| 種類 | 設定場所 | 規模 | 仕様 |
|---|---|---|---|
| (a) `omit` | `pyproject.toml` `[tool.coverage.run].omit` | 14 パターン / 174 ファイル / 2,342 statements | ファイル単位で分母から外す |
| (b) `exclude_lines` | `pyproject.toml` `[tool.coverage.report].exclude_lines` | 6 パターン / 実除外 276 行 | **行**を分母から外す |
| (c) `pragma: no cover` | ソース内インライン | 27 箇所 | (b) の第 1 パターンに一致して効く |

`branch = true` は carve-out ではなく測定方式。維持。

### 3.2 `omit` 全 14 パターンの扱い（Step 2〜3 で確定）

| パターン | 対象 | 扱い | 理由 |
|---|---|---|---|
| `*/tests/*` | — | **維持** | テストコード（定義として妥当） |
| `*/migrations/*` | 1 | **維持** | 手順ファイル |
| `*/alembic/*` | 30 | **維持** | 同上（954 statements） |
| `*/conftest.py` | — | **維持** | フィクスチャ定義 |
| `*/__pycache__/*` | — | **維持** | 生成物 |
| `src/__init__.py`<br>`src/*/__init__.py`<br>`src/*/*/__init__.py`<br>`src/*/*/*/__init__.py` | 141（1,377 stmts） | **要監査（§3.5）** | 「再エクスポートのみ」が前提。ロジックを含む 46 件は別途対応 |
| `src/services/age_client.py` | 1 | **維持（削除予定）** | 非推奨スタブ。`SHIM_REMOVAL_PLAN` の R 期で消滅 |
| `src/core/exceptions.py` | 1 | **維持（削除予定）** | 再エクスポート shim |
| `src/services/marketing.py` | 1 | **維持（削除予定）** | 再エクスポート shim |
| `src/schemas/easy_mode.py` | **0（ファイル不在）** | **削除（stale）** | `src/schemas/` には `__init__.py` のみ。存在しないパスを残すと「設定が生きて運用されている」錯覚を与える |

### 3.3 `exclude_lines` 全 6 パターンの扱い

| パターン | 扱い | 理由 |
|---|---|---|
| `pragma: no cover` | **維持** | インライン除外の入口。**理由コメント必須**（r3） |
| `def __repr__` | **維持** | 再現用の薄いメソッド。標準的 |
| `raise AssertionError` | **維持** | 到達不能の表明。標準的 |
| `raise NotImplementedError` | **維持（要注意）** | 「未実装」の表明。**実装が進むなら件数は減るべき**。増加は設計退行の兆候 |
| `if __name__ == .__main__.:` | **維持** | エントリポイント。標準的 |
| `if TYPE_CHECKING:` | **維持** | 型検査用 import。標準的 |

6 パターンとも一般的で現状に問題はない。**問題は「追加・変更がレビューを通らないこと」**なので、
仕様化の焦点は (a) と (c) に置く。

### 3.4 治理ルール（本計画で新設する 6 つ）

| ルール | 内容 | 機械的な強制手段 |
|---|---|---|
| **r1** | carve-out は 3 種類のみ。`.coveragerc` 追加・`--cov-config` 上書き・`--no-cov` 常態化を禁止 | `test_coverage_carveout_registry.py` が `.coveragerc` / `setup.cfg` の不在を assert |
| **r2** | 除外の追加・削除・変更は **`config/coverage_carveout_registry.json` と必ず同期**。差分があれば fail | 同テスト（`shim_registry.json` / `ci_lint_baseline.json` と同じ運用） |
| **r3** | `pragma: no cover` には理由コメント必須（`# pragma: no cover  # <理由>`）。理由なしは fail | 同テストが 27 箇所を走査 |
| **r4** | `fail_under` と **同時に** `omit` / `exclude_lines` を増やす PR は台帳 diff 必須（数字だけ上げる除外を禁止） | 同テストが pyproject の carve-out 節と台帳の**集合完全一致**を取る |
| **r5** | 測定スコープは `make coverage-ci` に一本化。CI とローカルは同一コマンド | `test_coverage_budget.py` が CI YAML と Makefile の `-m` 文字列一致を assert |
| **r6** | パッケージ別の下限（フロア）を `config/coverage_floors.json` で固定し、総合値だけを見ない | 同テストが JSON のフロアと実測を突合（§5） |

### 3.5 `__init__.py` omit の監査結果（AST ベース・Step 3 で台帳化）

許容: `Import` / `ImportFrom` / ドキュメント文字列 / 定数代入。
要監査: `FunctionDef` / `AsyncFunctionDef` / `ClassDef` / `If` / `For` / `While` / `Try` / `With` /
`Match`、および `Call`・`IfExp`・`Lambda` を含む代入（PEP 562 の `__getattr__` は `FunctionDef` に該当）。

| 区分 | 件数 | 扱い |
|---|---:|---|
| `__init__.py` 総数 | **141** | — |
| ロジック非含有（純粋な再エクスポートのみ） | **95** | omit 維持で問題なし |
| ロジック含有 | **46** | 下のとおり分類 |
| ├ **登録済み shim**（`config/shim_registry.json` 141 件に登録済み） | **32** | `SHIM_REMOVAL_PLAN` の R 期に本体ごと消滅。**omit 維持で可** |
| └ **非 shim でロジック含有** | **14（475 statements）** | **要対応** |

非 shim・ロジック含有 14 件（`src/agents` / `backend/database` ×2 / `backend/tasks` / `config` /
`core/container` / `domain/writing` / `easy_mode` / `infrastructure/repositories` /
`integrations/vector_store` / `models` / `publishing/publishers` / `services`（ルート） / `shared/utils`）。

対応方針（2 択、**`pragma` 追加は禁止**）:

1. **本体を通常モジュールへ移し、`__init__` を再エクスポートに戻す**（原則。移設先は
   `docs/MOVEMENT_MAPPING.md` の規約に従う）。
2. **`__init__` に直接テストを書く**（移設コストが見合わない場合。`__init__` の omit を
   該当ファイルだけ外すのは、台帳の `logic_bearing_init` に列挙する形で r2 に従う）。

> **注意**: 移設を選ぶと**分母が 475 statements 増えるため総カバレッジは一時的に下がる**
> （475 / 85,228 ≈ 0.56pt）。その場合でも `fail_under` を下げない（§7.4）。

---

## 4. 実装ステップ（全体像）

各ステップ = 1 コミット = **「変更 + リグレッション防止テスト + 完了条件」**で自己完結。
途中で止まっても閾値が下がらない（ラチェット）。

| Step | 内容 | `fail_under` | 主な成果物 | 見積 |
|---|---|---|---|---|
| **0** | 計測の一元化（3 系統 → `make coverage-ci`）＋マーカー整合の確認 | 60（据え置き） | `Makefile` / `ci.yml` | 0.5 日 |
| **1** | **閾値 60 → 75**（pyproject + CI の 2 箇所）＋ 予算固定型回帰テスト新設 | **75** | `tests/regression/test_coverage_budget.py` | 0.5 日 |
| **2** | carve-out 台帳の作成と r1〜r4 の強制 | 75 | `config/coverage_carveout_registry.json` + `test_coverage_carveout_registry.py` | 1 日 |
| **3** | stale 削除 ＋ `__init__` 監査台帳化（14 件の移設 or テスト） | 75（分母 +475 なら一時低下 → テストで補う） | `pyproject.toml` omit 節 / `docs/MOVEMENT_MAPPING.md` | 1〜2 日 |
| **4** | **パッケージ別フロア（r6）** の導入 | 75 | `config/coverage_floors.json` + フロア検査 | 1 日 |
| **5** | ラウンド A: **backend**（missing 6,174＝最大の杠杆）65.62 → 70 | 75 | `tests/unit/backend/**` 追加 | 3〜4 日 |
| **6** | ラウンド B: **nsfw / monitoring / presets / interfaces**（小規模で高効率） | 75 → 76 | 各パッケージのテスト新設 | 2 日 |
| **7** | ラウンド C: **分岐カバレッジ**（67.73% → 72%、異常系・エラー経路） | 76 → 77 | 上位 missing-branch ファイルの異常系テスト | 3 日 |
| **8** | ドキュメント整合 ＋ DoD 確認 | 77 | `docs/TEST_STRATEGY.md` / `PRODUCTION_DEPLOYMENT_CHECKLIST.md` | 0.5 日 |

**Step 1 だけで「60→75」の要求は満たされる**。Step 2〜4 が治理（本計画の核心）、
Step 5〜7 が「総合値に隠れた弱さ」への実作業。

### 4.1 全 Step 共通の完了条件（Definition of Done）

```bash
# (1) カバレッジゲート（測定 1 回 + 総合/フロアの検査）が新しい閾値で通る
make verify-coverage      # = coverage-ci（測定 + fail_under=75）→ coverage_gate テスト
                          # → coverage.json が無い・古ければここで落ちる

# (2) 本 Step のリグレッション防止テストが緑
#     （coverage_gate のテストは (1) が担う。それ以外はここ）
.venv/bin/python3 -m pytest tests/regression/<本Stepのテスト> -q --timeout=300

# (3) 既存の回帰テストが壊れていない（既知失敗 8 件を増やさない）
#     coverage_gate は coverage.json を読むため除外し、(1) で検査する
.venv/bin/python3 -m pytest tests/regression -m "not coverage_gate" -q --timeout=300
.venv/bin/python3 -m pytest tests/unit -q --timeout=120

# (4) lint 予算を増やしていない（新規テストの未使用 import 等が F401 に化けると
#     tests/regression/test_lint_budget.py の LINT_ERROR_BUDGET=122 で落ちる）
.venv/bin/python3 -m ruff check src tests --statistics
```

**既知失敗の固定**: `tests/regression/` の既知失敗は 8 件
（`test_conftest_fixtures` / `test_docs_router_count_matches_reality` /
`test_subprocess_encoding_gate` / `test_tier_quality_gate` ×4 / `test_v5_version_consistency`）。
本計画の全 Step で **failed 数が 8 を超えないこと**を完了条件に含める。

> **適用開始は Step 1**: `make verify-coverage` と `coverage_gate` マーカーは Step 1 で生まれる。
> **Step 0 では (1) の代わりに `make coverage-ci`** を使い、(3) は
> `-m "not coverage_gate"` なしで実行してよい（その時点でマーカーが無いので差は出ない）。

> **実測時の注意**: 本計画の測定ランでは 20 failed だった（うち 3 件が上記既知、
> 残り 17 件はローカルに PostgreSQL / Redis が無いための環境依存失敗:
> `tests/e2e` ×3、`tests/security` IDOR ×2・route mount parity ×2、
> `tests/contract` v6 ×2、`tests/database` ×1、`tests/generation` ×1、
> `tests/perf|performance` ×2、`tests/regression` v53 ×1、`tests/unit/backend` ×1 ほか）。
> CI ではサービスコンテナが在るため通るはずだが、**Step 1 のフロア定数は CI の初回実測で確定する**
> （§6 Step 1）。

---

## 5. パッケージ別フロア（r6）

総合値 78.11% は `backend` の 65.62% を隠している。**総合閾値だけでは弱い内訳を検出できない**ので、
パッケージ別の下限を `config/coverage_floors.json` で固定する。

### 5.1 設計：2 段構え（守り / 攻め）

| 段 | 対象 | 値 | 目的 |
|---|---|---|---|
| **守り（ratchet）** | 全 35 パッケージ | **実測値 − 1.0pt**（下限は 50pt） | 悪化の即時検出。**新しいテストを書かずに導入できる**（実測値を台帳に固定するだけ） |
| **攻め（floor）** | 下位 5 パッケージ（nsfw / monitoring / presets / interfaces / backend） | Step 5〜7 の到達目標 | 弱点の是正。各 Step の完了条件 |

守りの導入で、**「どこかのパッケージが 1pt 以上落ちたら CI が赤くなる」**という
現在存在しない検出力を即座に得られる。これが Step 4 の狙い。

### 5.2 守りフロアの初期値（2026-11-08 実測 − 1.0pt）

`nsfw 33.8` / `monitoring 44.2` / `presets 51.8` / `interfaces 60.5` / `backend 64.6` /
`pipeline 68.7` / `infrastructure 69.1` / `application 69.8` / `agents 75.3` / `config 75.9` /
`llm 76.6` / `core 77.4` / `services 77.6` / `cli 78.1` / `audit 80.1` / `integrations 80.1` /
`fusion 81.7` / `stores 83.2` / `models 83.3` / `engine 84.7` / `shared 84.8` / `annotations 85.1` /
`domain 86.0` / `narrative 87.3` / `generation 87.6` / `src 88.5` / `rules 90.4` / `utils 91.1` /
`narrative_balancer 91.1` / `publishing 91.3` / `security 93.1` / `easy_mode 94.3` / `api 95.5` /
`logging 100.0` / `plugins 100.0`

> 守りフロアは **CI の初回実測後に確定**する（ローカルと CI で値が変わるため）。
> ローカル値をそのまま使うと CI が赤くなる可能性がある。手順は §6 Step 4 に記載。

### 5.3 攻めフロア（Step 5〜7 の目標）

| パッケージ | 現状 | 目標 | 必要な追加カバー量（単位） | 概算テスト数 |
|---|---:|---:|---:|---:|
| backend | 65.62 | **70.0** | 約 790 単位（全体 +0.93pt） | 10〜14 ファイル |
| nsfw | 34.82 | **60.0** | 約 73 単位 | 3〜4 ファイル（`erotic_vocabulary` 406 行が中心） |
| interfaces | 61.46 | **70.0** | 約 47 単位 | 2〜3 ファイル（`streamlit_adapter` 87 stmts が 3.60%） |
| monitoring | 45.16 | **70.0** | 約 16 単位 | 1〜2 ファイル |
| presets | 52.81 | **70.0** | 約 32 単位 | 1〜2 ファイル |

小規模 4 パッケージ（nsfw / interfaces / monitoring / presets）は **合計で約 168 単位 = 全体 +0.20pt** しか
動かないので、**効率より「フロアを守れる状態にすること」が目的**。真に全体を動かすのは `backend`（+7.24pt の余地）。

### 5.4 ラウンド A（Step 5 / backend）の対象ファイル上位

missing 単位の大きい順（実測）:

| ファイル | missing 行 | 現在 | 備考 |
|---|---:|---:|---|
| `src/backend/tasks/generation_tasks.py` | 230 | 23.46% | 生成タスク（統合テスト残件と重なる領域） |
| `src/backend/routers/multimedia.py` | 183 | 24.92% | |
| `src/backend/routers/branches.py` | 121 | 77.13% | 1,371 行・全体最大ファイル。分岐が大量に未到達（missing branch 70） |
| `src/backend/engine_critique.py` | 108 | 7.41% | |
| `src/backend/tasks/commercial_tasks.py` | 103 | 27.72% | |
| `src/backend/engine_utils.py` | 102 | 26.00% | missing branch 46/52 |
| `src/backend/routers/billing_webhook.py` | 98 | 55.19% | **決済 webhook＝実リスク高** |
| `src/backend/engine_narrative.py` | 96 | 38.55% | |
| `src/backend/routers/orchestrated.py` | 94 | 30.73% | |
| `src/backend/sse.py` | 89 | 8.13% | |
| `src/backend/engine_context.py` | 88 | 63.21% | |
| `src/backend/routers/commercial.py` | 87 | 50.86% | |
| `src/backend/patch_validator.py` | 85 | 11.92% | |
| `src/backend/observability/metrics.py` | 78 | 52.44% | |
| `src/backend/routers/tasks.py` | 78 | 46.00% | |

**優先順位の基準（明示する）**: (1) 実運用リスク（`billing_webhook` / `patch_validator` / `sse`）、
(2) missing 量、(3) 既存テストの近さ。`generation_tasks` は統合テスト残件と重なるため
**後回し**にする（ゲート化の別計画と作業が重複する）。

### 5.5 ラウンド C（Step 7 / 分岐）の対象ファイル上位

missing branch の大きい順:

| ファイル | missing/total branch | 含意 |
|---|---:|---|
| `src/backend/sanitizer.py` | 75 / 314 | 入力サニタイザ＝異常系が本分 |
| `src/agents/illustration_agent.py` | 92 分岐中 75 未到達 | |
| `src/integrations/rag/rag_service.py` | 142 分岐中 74 | |
| `src/models/audit.py` | 80 分岐中 71 | |
| `src/agents/plot.py` | 68 分岐中 **68（全滅）** | 15.38% |
| `src/engine/graph/networkx_store.py` | 66 分岐中 **66（全滅）** | 9.62% |
| `src/core/interfaces.py` | 108 分岐中 54 | |
| `src/backend/patch_validator.py` | 48 分岐中 **48（全滅）** | 11.92% |

「分岐が 100% 未到達」のファイルは**行もほぼ未カバー**なので、ラウンド A/B で行を埋めれば
分岐も同時に動く。**分岐特有の作業が必要なのは `sanitizer.py`・`rag_service.py`・`models/audit.py`
など「行は通るが片側の分岐だけ未到達」のファイル**であり、これは**異常系・エラー経路のテスト**を
意味する（正常系を再実行しても埋まらない）。

---

## 6. 各ステップの詳細手順

### Step 0: 計測の一元化とスコープ固定

**変更**

1. `Makefile` に `coverage-ci` ターゲットを追加。**CI の test ジョブと文字列レベルで一致**させる。

   ```make
   # .github/workflows/ci.yml:126 と文字列一致させること（r5 でテストされる）。
   # `not coverage_gate` は Step 1 で追加する（測定済み coverage.json を読むテストは
   # 測定実行から除外しなければ「JSON がまだ無い」で落ちるため）。
   COV_SCOPE = -m "not integration and not perf and not slow"
   COV_ARGS  = --cov=src --cov-report=term-missing --timeout=180

   coverage-ci:  ## CI と同一コマンドでカバレッジを測る（本計画の唯一の正）
   	$(PYTHON) -m pytest -q $(COV_SCOPE) $(COV_ARGS)
   ```

2. `.github/workflows/ci.yml:126` を同じ `COV_SCOPE` / `COV_ARGS` に寄せ、
   `--cov-fail-under` のみ差分として残す（Step 1 で 75 に更新）。
   Makefile 変数と YAML の一致は人手依存なので、**CI を `make coverage-ci` 経由にする**のが最善
   （YAML が `run: make coverage-ci` になれば一致は構造的に保証される）。

3. `make test-unit`（`Makefile:62`）の `--cov-fail-under=60` を**削除**する。
   `tests/unit` という部分集合に全体閾値を掛けるのは誤りで、テストの偏りを招く。
   カバレッジは `coverage-ci` に任せる。

4. **マーカー整合の確認（スコープ固定の前提）**: `tests/perf/`・`tests/performance/` の
   未付与ファイルに `@pytest.mark.perf` を付けるか、**付与しない方針を明文化**する。
   - 付与する場合: 測定対象から外れるので**総カバレッジが変わる**。Step 1 のフロア確定前に実施すること。
   - 付与しない場合: `docs/TEST_STRATEGY.md` に「`tests/perf/` と `tests/performance/` は
     marker ではなくディレクトリで区別し、カバレッジ測定に含める」と明記する。
   - **どちらでもよいが、決めてから Step 1 に進む**（測定値が変わるため）。

5. **`--timeout` の引き上げ**: coverage 付与でテストは遅くなるため、CI の
   `--timeout=120` → `180`（`COV_ARGS` に含める）。**この引き上げは Step 0 で行い、
   Step 1 の閾値変更より前に確定する**（測定値が変わる要因を先に消す）。
6. `scripts/measure_coverage.py` / `run_full_coverage.py` / `coverage_summary.py` /
   `_total_coverage.py` / `analyze_coverage.py`（計 232 行・5 本）は `scripts/coverage/` に移設し、
   1 本のエントリポイントへ集約する。5 本はいずれも「`coverage.json` を読んで集計する」同一作業の
   断片で、互いに異なる前提（`-m` フィルタ有無・`json-report.json` の有無）を持っている。
   **移設時に shim は残さない**（内部スクリプトであり `config/shim_registry.json` の対象外。
   `test_repo_hygiene` / `test_H1_gitignore_tightness` に引っかからないことを確認）。

**リグレッション防止テスト**: `test_coverage_budget.py`（Step 1）の
`test_ci_and_makefile_use_identical_scope()`。

**完了条件**: `make coverage-ci` が CI と同値。`make test-unit` はカバレッジを測らない。

---

### Step 1: 閾値 60 → 75 と予算固定型回帰テスト

**変更**

1. `pyproject.toml` `[tool.coverage.report].fail_under = 60` → **`75`**
2. `.github/workflows/ci.yml:126` `--cov-fail-under=60` → **`--cov-fail-under=75`**
   （Step 0 で `make coverage-ci` 経由にしていれば Makefile 側も自動追従）
3. `pytest.ini` の `markers` に `coverage_gate` を登録する:

   ```ini
   coverage_gate: 測定済み coverage.json を読むゲートテスト。測定を伴う実行からは除外する
   ```

4. **`COV_SCOPE`（Makefile と ci.yml の両方）を更新する**:

   ```
   -m "not integration and not perf and not slow and not coverage_gate"
   ```

   理由: `test_coverage_budget.py` は**測定後の `coverage.json` を読む**ため、
   測定を伴う実行（`coverage-ci`）の中で走ると「JSON がまだ無い」で必ず落ちる。
   マーカーで測定実行から外し、**検査だけを別実行（Step 1b）に回す**。
   （`-m` の文字列は Makefile と ci.yml の両方が同じであることを r5 のテストが検査する。）
5. **CI の `test` ジョブを 2 ステップに分ける**（下記「測定とフロア検査の分離」）。
6. `Makefile` に `verify-coverage` ターゲットを追加
   （`coverage-ci` → `COVERAGE_JSON=coverage.json pytest -m coverage_gate tests/regression/test_coverage_budget.py`）。
7. `tests/regression/test_coverage_budget.py` を新規作成（`test_lint_budget.py` の雛形：
   **上限固定 → 下限固定**に読み替える。ファイル冒頭に
   `pytestmark = pytest.mark.coverage_gate` を置く）。

**テストの構成（重要: 測定を 2 回しない）**

CI は「測定」と「フロア検査」を **1 回の coverage 実行**で済ませる:

```
Step 1a: pytest -m "not integration and not perf and not slow and not coverage_gate" \
             --cov=src --cov-report=json:coverage.json --cov-fail-under=75   # 測定 + 総合ゲート
Step 1b: COVERAGE_JSON=coverage.json \
             pytest -m coverage_gate tests/regression/test_coverage_budget.py  # JSON を読むだけ（数秒）
```

Step 1a は **`coverage_gate` を除外する**（§6 Step 1 の変更 4 の理由）。
Step 1b は **測定しない**（`--cov` を付けない）ので、同じ coverage 実行を 2 回走らせない。

ローカルは `make verify-coverage` がこの 2 段を繋ぐ。
`test_coverage_budget.py` は **`coverage.json` を読む**（測定を自分で走らせない）。
ファイルが無ければ「先に `make coverage-ci` を実行せよ」と明示的に fail する。
**スキップにしない**（スキップは「緑に見える」だけなので本リポジトリの規約に反する）。

> **補足**: `coverage_gate` マーカーを外した `pytest tests/regression` の実行では
> このファイルは**実行されない**。§4.1 (3) の非回帰確認は
> `pytest tests/regression -m "not coverage_gate"` を使い、
> 代わりに `make verify-coverage` で必ず検査する（網羅を 1 箇所に寄せる）。

**`tests/regression/test_coverage_budget.py` の内容（＝Step 4 追加後の最終形）**

> **実装順序の注意**: 下のコードには `test_per_package_floors` と `FLOORS_FILE` が含まれるが、
> `config/coverage_floors.json` は **Step 4 で作成する**。Step 1 の時点ではこの 2 つが無いので、
> **Step 1 では上 4 テスト（`test_fail_under_is_consistent_between_pyproject_and_ci` /
> `test_fail_under_meets_plan_d_target` / `test_ci_and_makefile_use_identical_scope` /
> `test_measured_coverage_meets_floor`）だけを実装**し、
> `test_per_package_floors` は **Step 4 の最初のコミットで追加**する。
> （Step 1 で先に足すと `config/coverage_floors.json` が無いため赤くなり、
> 「赤を放置する」習慣を作るため、追加は必ず Step 4 に置く。）

```python
"""カバレッジが下限・フロアを割らないことの回帰テスト（lint_budget のカバレッジ版）。

PLAN_D Step 1。

測定はしない。CI / make coverage-ci が書き出した coverage.json を読むだけ
（測定を 2 回すると実行時間が倍になるため）。JSON が無い・古ければ fail する。
"""

from __future__ import annotations

import json
import os
import re
import time
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: 測定を伴う実行（coverage-ci）からはこのファイルを除外する。
#: coverage.json は測定の**最後**に書き出されるため、同じ実行の中では読めない。
pytestmark = pytest.mark.coverage_gate

#: 測定スコープ（Step 0 の Makefile COV_SCOPE と文字列一致 / r5）
SCOPE_NEEDLE = "not integration and not perf and not slow"
#: 測定実行から外すマーカー（Step 1 の変更 4）
GATE_EXCLUSION_NEEDLE = "not coverage_gate"

#: 本テスト作成時点の実測（2026-11-08, coverage 7.17.0 / branch=true）
#: 総合値の下限。閾値(fail_under)より高く設定し、「閾値通過」ではなく
#: 「実測が落ちていない」を検出する。
MEASURED_FLOOR = 77.0        # ← CI 初回実測で確定（§6 Step 1 手順 5）

#: パッケージ別フロア（config/coverage_floors.json と同期 / r6）
FLOORS_FILE = ROOT / "config" / "coverage_floors.json"

#: 清新さ: 古い coverage.json を信じない
MAX_JSON_AGE_SECONDS = 6 * 3600


def _load_coverage_json() -> dict:
    path = Path(os.environ.get("COVERAGE_JSON", ROOT / "coverage.json"))
    assert path.exists(), (
        f"{path} が無い。先に `make coverage-ci` を実行すること"
        "（このテストは測定を代行しない。測定を 2 回すると CI が倍になる）。"
    )
    age = time.time() - path.stat().st_mtime
    assert age < MAX_JSON_AGE_SECONDS, (
        f"coverage.json が {age/3600:.1f} 時間古い。再測定せよ。"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_fail_under_is_consistent_between_pyproject_and_ci():
    """pyproject の fail_under と CI の --cov-fail-under が一致していること（r5）。"""
    with open(ROOT / "pyproject.toml", "rb") as f:
        current = tomllib.load(f)["tool"]["coverage"]["report"]["fail_under"]
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = re.search(r"--cov-fail-under=(\d+)", ci)
    assert m, "ci.yml に --cov-fail-under がない"
    assert int(m.group(1)) == current, (
        f"閾値が2箇所で不一致: pyproject={current} / ci.yml={m.group(1)}"
    )


def test_fail_under_meets_plan_d_target():
    """PLAN_D の目標（75）を下回る閾値への変更を検出する。"""
    with open(ROOT / "pyproject.toml", "rb") as f:
        current = tomllib.load(f)["tool"]["coverage"]["report"]["fail_under"]
    assert current >= 75, (
        f"fail_under={current} が PLAN_D の目標 75 を下回る。"
        "引き下げは PLAN_D の逸脱として理由の記載が必要。"
    )


def test_ci_and_makefile_use_identical_scope():
    """CI と make coverage-ci の測定スコープが同一であること（r5 / Step 0）。"""
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for label, text in (("Makefile", makefile), ("ci.yml", ci)):
        assert SCOPE_NEEDLE in text, f"{label} の測定スコープに '{SCOPE_NEEDLE}' が無い"
        assert GATE_EXCLUSION_NEEDLE in text, (
            f"{label} の測定スコープに '{GATE_EXCLUSION_NEEDLE}' が無い。"
            "測定実行の中で coverage_gate を走らせると coverage.json が未生成のため必ず落ちる。"
        )


def test_measured_coverage_meets_floor():
    """実測総カバレッジが下限を割らないこと（悪化すると落ちる）。"""
    data = _load_coverage_json()
    total = data["totals"]["percent_covered"]
    assert total >= MEASURED_FLOOR, (
        f"カバレッジが下限 {MEASURED_FLOOR}% を下回った: 実測 {total:.2f}%。"
        "疑うべき原因（優先順）: (1) pyproject.toml の omit/exclude_lines が増えたか "
        "(2) テストが消えたか (3) 測定スコープが変わったか。"
        "git diff で pyproject.toml と tests/ を確認すること。"
    )


def test_per_package_floors():
    """パッケージ別の下限を割らないこと（r6 / 総合値に隠れた悪化を検出）。

    指標は fail_under と同じ「行 + 分岐」（branch=true の総合値と同じ定義）。
    行だけで判定すると分岐の悪化を取りこぼすため、必ず branches を含める。
    """
    data = _load_coverage_json()
    floors = json.loads(FLOORS_FILE.read_text(encoding="utf-8"))["floors"]
    actual: dict[str, list[int]] = {}
    for f, s in data["files"].items():
        parts = f.split("/")
        pkg = parts[1] if len(parts) > 2 else parts[0]
        su = s["summary"]
        a = actual.setdefault(pkg, [0, 0, 0, 0])
        a[0] += su["num_statements"]
        a[1] += su["covered_lines"]
        a[2] += su["num_branches"]
        a[3] += su.get("covered_branches", 0)
    violations = []
    for pkg, floor in floors.items():
        ns, cl, nb, cb = actual.get(pkg, [0, 0, 0, 0])
        if ns + nb == 0:
            violations.append(f"{pkg}: 測定対象が存在しない（フロア {floor} に対して0単位）")
            continue
        pct = (cl + cb) / (ns + nb) * 100
        if pct < floor:
            violations.append(f"{pkg}: {pct:.2f}% < フロア {floor}%")
    assert not violations, "パッケージ別フロア違反:\n" + "\n".join(violations)
```

**フロアの指標（明示）**: `test_per_package_floors` は **`fail_under` と同じ「行 + 分岐」**
の指標で判定する（§1.5 の表と同じ定義）。行だけで判定すると分岐の悪化を取りこぼす。
分岐**単独**（branch-only、現状 67.73%）のフロアは、§1.1 の開き（行 80.92% との 13.19pt）を
放置しないために **Step 7 で `branch_only_floors` として追加**する（段階的に複雑化させる）。

**`MEASURED_FLOOR` の確定手順（実装者が必ず行う）**

1. Step 0 のスコープ確定後、CI で 1 回実行する。
2. CI の jobログから `TOTAL ... %`（`--cov-report=term-missing` の最終行）を読み取る。
3. その値から **1.0pt 引いた数**を `MEASURED_FLOOR` に設定する
   （例: CI が 78.4% なら `MEASURED_FLOOR = 77.4`）。
4. **CI の 2 回目の実行でこのテストが緑であることを確認してから**コミットする。
   2 回目が赤なら、環境差（実行順・サービス有無）が 1pt 超えているので、
   フロアを 1.0 → 2.0 に広げ、**その旨をこのテストの docstring に記録する**。

**完了条件**: 4 テスト（+Step 4 で 2 テスト追加）が緑。
**手動確認**: `fail_under` を **74** に下げると `test_fail_under_meets_plan_d_target` が赤になることを
確認してからコミットする（テストが本当に機能していることの証明。**確認後は 75 に戻す**）。

---

### Step 2: carve-out 台帳と r1〜r4 の強制

**成果物 1**: `config/coverage_carveout_registry.json`

```json
{
  "$comment": "PLAN_D Step 2: カバレッジ除外（carve-out）の仕様台帳。変更は test_coverage_carveout_registry.py とセットで。",
  "omit": [
    {"pattern": "*/tests/*",             "reason": "テストコードは測定しない", "kind": "definition"},
    {"pattern": "*/migrations/*",        "reason": "マイグレーションは手順ファイル", "kind": "definition"},
    {"pattern": "*/alembic/*",           "reason": "同上", "kind": "definition"},
    {"pattern": "*/conftest.py",         "reason": "フィクスチャ定義", "kind": "definition"},
    {"pattern": "*/__pycache__/*",       "reason": "生成物", "kind": "definition"},
    {"pattern": "src/__init__.py",       "reason": "再エクスポート専用（Step 3 で監査済み）", "kind": "reexport"},
    {"pattern": "src/*/__init__.py",     "reason": "同上", "kind": "reexport"},
    {"pattern": "src/*/*/__init__.py",   "reason": "同上", "kind": "reexport"},
    {"pattern": "src/*/*/*/__init__.py", "reason": "同上", "kind": "reexport"},
    {"pattern": "src/services/age_client.py",    "reason": "非推奨スタブ（SHIM_REMOVAL_PLAN で削除予定）", "kind": "shim"},
    {"pattern": "src/core/exceptions.py",        "reason": "再エクスポート shim（同上）", "kind": "shim"},
    {"pattern": "src/services/marketing.py",     "reason": "再エクスポート shim（同上）", "kind": "shim"}
  ],
  "exclude_lines": [
    {"pattern": "pragma: no cover",          "reason": "インライン除外の入口", "kind": "definition"},
    {"pattern": "def __repr__",              "reason": "再現用の薄いメソッド", "kind": "definition"},
    {"pattern": "raise AssertionError",      "reason": "到達不能の表明", "kind": "definition"},
    {"pattern": "raise NotImplementedError", "reason": "未実装の表明（増加は設計退行の兆候）", "kind": "watch"},
    {"pattern": "if __name__ == .__main__.:", "reason": "エントリポイント", "kind": "definition"},
    {"pattern": "if TYPE_CHECKING:",         "reason": "型検査用 import", "kind": "definition"}
  ],
  "pragma_no_cover": {"max_count": 27, "reason_required": true},
  "logic_bearing_init": []
}
```

> `src/schemas/easy_mode.py` は**台帳に載せない**（存在しない＝stale。Step 3 で pyproject から削除）。
> `logic_bearing_init` は Step 3 で 14 件を埋める。

**成果物 2**: `tests/regression/test_coverage_carveout_registry.py`

| テスト | 検査するルール | 実装の要点 |
|---|---|---|
| `test_no_alternate_coverage_config_files` | r1 | `.coveragerc` / `setup.cfg` / `.coveragerc.local` が存在しないこと。pyproject 内の `[tool.coverage.*]` が `run` / `report` / `html` の 3 節のみであること |
| `test_pyproject_carveouts_match_registry` | r2 / r4 | tomllib で `omit` / `exclude_lines` を読み、台帳の pattern 集合と**完全一致**を取る。片方だけ増えたら fail |
| `test_every_pragma_has_a_reason` | r3 | `src/**/*.py` を走査し、`pragma: no cover` を含む行と**直前の行**のいずれかに `#` の理由があること |
| `test_pragma_count_within_budget` | r3 | pragma 件数 ≤ 27。**削減は歓迎（上限はそのまま）** |
| `test_registry_shape_is_valid` | r2 | 全エントリに `pattern` / `reason` / `kind` があり、`kind` が `definition` / `reexport` / `shim` / `watch` のいずれかであること |

**既存 pragma 27 箇所への理由付け（Step 2 の一部）**

分布: `src/engine/foreshadowing/kpi.py`(5) / `src/services/digest_service.py`(3) /
`src/integrations/rag/embedding_service.py`(2) / `src/engine/anti_ai/orchestrator.py`(2) /
単発 18 ファイル。

理由は「この行がなぜテスト不要なのか」を書く。**「テスト書きたくない」は理由にならない**。
書けないものは pragma を外してテストを書き、Step 5〜7 の対象にする。

**完了条件**: 台帳と pyproject が一致。pragma 27 箇所すべてに理由が付き、テストが緑。

---

### Step 3: stale 削除・`__init__` 監査の台帳化

**変更**

1. `pyproject.toml` の omit から `"src/schemas/easy_mode.py"` を削除（stale）。
   **削除前後で `make coverage-ci` の値が変わらないこと**を確認する
   （不在パスの omit は無作用のはず。**もし値が変わったら設定の読み込み経路に問題がある**。
   その場合は止まって調査する。数字を無視して先へ進まない）。
2. §3.5 の監査結果 14 件を台帳の `logic_bearing_init` に固定する
   （`file` / `statements` / `kind`（`lazy_export` / `factory` / `class`） / `action`（`move` / `test`））。
3. 14 件のうち `action: move` を選んだものについて、本体を通常モジュールへ移設する
   （`docs/MOVEMENT_MAPPING.md` の規約に従う。**shim は残さない**＝この 14 件は shim ではない）。
4. `test_coverage_carveout_registry.py` に `test_logic_bearing_init_registered` を追加
   （`__init__.py` を再走査し、ロジック含有件数が台帳と一致すること）。

**分母の変化**: 移設すると最大 +475 statements（≈ +0.56pt の分母増）。
**`fail_under` は 75 のまま**。総合値が 77 を割ったら、§6 Step 1 のフロア確定手順に戻って
`MEASURED_FLOOR` を実測に合わせ、**同時にテストで埋める計画を立てる**（引き下げでごまかさない）。

**完了条件**: `make coverage-ci` の値の変化を説明でき、台帳 3 節が緑。

---

### Step 4: パッケージ別フロア（r6）の導入

**変更**

1. `config/coverage_floors.json` を作成（§5.2 の「実測 − 1.0pt」を初期値とする）。
2. `test_coverage_budget.py` に `test_per_package_floors()` を追加（§6 Step 1 のコード参照）。
3. CI の Step 1b にこのテストが含まれるよう、既存の `test` ジョブの順序を確認する。

**初期値の確定手順（Step 1 の `MEASURED_FLOOR` 確定と同じ回で行う）**

1. CI の初回実測から**パッケージ別の line%** を取得する
   （`--cov-report=json` の `files[*].summary` を集計する 10 行のスクリプトを
   `scripts/coverage/floors.py` に置く。**これは集計のみで測定しない**）。
2. その値 − 1.0pt を `config/coverage_floors.json` に書き込む。
3. CI 2 回目で緑であることを確認してからコミットする。
4. **`logging` / `plugins` / `security` のような小規模（15〜135 statements）パッケージは
   フロアの幅を 1.0 → 2.0pt にする**（サンプルが小さく 1 テストの追加で大きく動くため）。

**リグレッション防止テスト**: `test_per_package_floors`（§6 Step 1）。
**手動確認**: `config/coverage_floors.json` の某パッケージのフロアを実測 +5pt に書き換えると
赤になることを確認してからコミットする。

**完了条件**: 全 35 パッケージのフロアが緑。CI 2 回連続で緑。

---

### Step 5〜7: テスト追加ラウンド（型は共通）

3 つのラウンドは**同じ型の作業**なので、1 Step = 1 パッケージ（または 1 ファイル群）に固定する。

**1 ファイル分の手順（低性能 LLM でも追える粒度）**

1. **対象を 1 つ選ぶ**: §5.4 / §5.5 の表、または
   `python -c "import json;d=json.load(open('coverage.json'));..."` で missing 上位から 1 つ。
2. **既存テストを探す**: `grep -rl "<対象モジュール>" tests/` で近いテストがあれば**拡張する**
   （新規ファイルを増やしすぎない）。無ければ `tests/unit/<pkg>/test_<module>.py` を新規作成。
3. **テストを書く**: `docs/TEST_STRATEGY.md` の禁止ルールに従う
   （恒真 assert 禁止／ソース grep を assert にする禁止／assert 0 個の禁止／
   **モックで戻り値を固定して実装を複製しない**）。
   **異常系・エラー経路・分岐の片側を必ず 1 本含める**（§5.5 の理由）。
4. **実行**: `.venv/bin/python3 -m pytest tests/unit/<pkg>/test_<module>.py -q --timeout=120`
5. **カバレッジ確認**: `make coverage-ci` を再実行し、対象ファイルの % が上がったこと・
   総合値が下がらなかったことを確認する。
6. **フロア更新（必要な場合のみ）**: 対象パッケージのフロアを**実測値 − 1.0pt** に更新する。
   **フロアを下げる（実測が下がった場合）は禁止**。下がったら原因を特定して埋める。
7. **完了条件**（§4.1 の 4 コマンド）を満たしてコミット。

**ラウンドごとの目標**（§5.3）:

| Step | 対象 | 目標 | 到達確認 |
|---|---|---|---|
| 5 | `backend` | line% 68.87 → **70.0+** | `config/coverage_floors.json` の backend を更新して緑 |
| 6 | `nsfw` / `monitoring` / `presets` / `interfaces` | 各 line% → **60.0+**（monitoring / presets は 60、interfaces は 70） | 同上 |
| 7 | 分岐（`sanitizer` / `rag_service` / `models/audit` / `patch_validator` / `networkx_store`） | branch-only 67.73 → **72.0+** | `config/coverage_floors.json` に `branch_only_floors` を追加して緑 |

**Step 7 の分岐単独フロア追加**: Step 4 の「行 + 分岐」フロアの実装が安定した後で、
`branch_only_floors` キーを追加し `test_per_package_floors` に分岐単独の判定を足す。
**この拡張は Step 7 の最初のコミット**とし、拡張直後に全フロアが緑であることを確認する
（一括で赤くならないように、初期値は実測 − 1.0pt）。

---

### Step 8: ドキュメント整合と DoD

**変更**

1. `docs/TEST_STRATEGY.md`: 「カバレッジ閾値の漸進的向上（55% → 65% → 75%）」を
   **実績に更新**する（`75% 到達（2026-11-08 実測 78.11% / fail_under=75）`、
   および r1〜r6 の治理ルールへの参照を追加）。
2. `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md:84`: `--cov-fail-under=60` → `75`。
3. `docs/STATUS.md:74,95`: `make test-unit` の記述（カバレッジ 40 ゲート）を現状に合わせる
   （Step 0 で `test-unit` はカバレッジを測らなくなったため）。
4. `docs/PLAN_D_COVERAGE_75.md`（本ファイル）に「実績」節を追記する。

**完了条件**: §10 の DoD チェックリスト全項目。

---

## 7. リスクと対策

### 7.1 「カバレッジ稼ぎ」による低品質テストの混入（最大リスク）

閾値を上げると数字を稼ぐ**何も検査しないテスト**が書かれやすい。本リポジトリには
発生実績と検知器が両方ある。

- 発生実績: H1 精査で「恒真 assert」「ソース grep を assert にする」「assert 0 個のテスト」が
  7 ファイル 11 箇所（`docs/TEST_STRATEGY.md` §緑が緑を保証しないテストの排除ルール）。
- 検知器: `tests/regression/test_H1_tautology_guard.py`。
- **対応**: Step 5〜7 の各 Step の完了条件に
  (i) `test_H1_tautology_guard.py` が緑、
  (ii) **既存の挙動を壊す変更を入れたときに赤になること**（変異テスト的確認：対象関数の
  戻り値を 1 箇所変えて赤になるかを手動確認する）を追加する。
  カバレッジは**副作用**として得られ、**目的にしない**。

### 7.2 分母の恣意的縮小（数字だけ上げる除外）

`omit` を増やせばカバレッジは上がる。最悪の不正行為である。

- **対策**: r2 / r4（台帳と pyproject の**集合完全一致**）。台帳を更新しなければ設定変更は必ず赤。
- **台帳自体の変更は PR diff で人が見る**（機械化できない部分。この設計に意図がある）。
- **追加の検知**: `MEASURED_FLOOR`（§6 Step 1）が、分母がおかしいと総合値の異常として表れる。

### 7.3 統合テストゲート化（評価優先 1 位）との相互作用

将来 `integration-observe` をゲート化すると統合テストが測定に加わり得る。

- **測定スコープは `-m "not integration and not perf and not slow and not coverage_gate"`
  に固定し続ける**（本計画の全 Step がこのスコープ、r5 で機械的に検査）。
- 統合ゲート化の別計画では**統合テストの成否**をゲートにするのであって、
  **カバレッジを統合込みで再測定しない**。再測定するなら統合込みの `fail_under` を
  別立てで定義し、本計画の値と混ぜない。

### 7.4 分母の増加（移設・omit 削除）で閾値を割り込む

Step 3 の移設は最大 +475 statements（−0.56pt）。`fail_under` を下げるのは禁止。

- **対策**: 分母が増える変更は **必ずカバー量の増加とセット**にする（移設した関数にテストを付ける）。
  セットにできない場合は、その変更を独立したコミットにし、**次のラウンドで埋める**ことを
  コミットメッセージに明記する。
- **禁止事項**: `fail_under` の引き下げ／`MEASURED_FLOOR` の引き下げでごまかす。

### 7.5 測定の非決定性（同じコマンドで値がぶれる）

- **原因**: テスト実行順依存（`tests/regression/test_integration_order_dependency.py` が部分対策）、
  マーカーの追加・変更（§1.3）、pytest-xdist 並列化の有無、conftest の遅延初期化。
- **対策**: スコープを文字列固定（r5）。**並列化（pytest-xdist）は本計画では導入しない**
  （結果の同一性が未検証のまま閾値を動かさないため）。導入は別 Step として、
  `MEASURED_FLOOR` と一致することを確認してから。
- **フロアの初期値は必ず CI で確定する**（§6 Step 1 / Step 4 の手順）。ローカル値を流用しない。

### 7.6 実行時間の増加

coverage 付与は pytest を遅くする（実測 16 分 44 秒 / 9,502 passed、対象 85,228 単位）。

- **対策**: 測定は **1 回だけ**（§6 Step 1 の「測定とフロア検査を分離」設計）。
  `test_coverage_budget.py` は JSON を読むだけで数秒で終わる。
- `--timeout=180` は CI の現行値（120）から引き上げる（coverage 付与で遅延するため）。
  **この引き上げは Step 0 で行い、Step 1 の測定前に確定する**。

### 7.7 既知失敗 8 件との関係

`tests/regression/` の既知失敗 8 件は本計画で**解消しない**（別問題）。
ただし §4.1 のとおり **failed 数 8 を上限**として各 Step で確認する。

---

## 8. 検証コマンド

```bash
# --- 測定（CI と同一コマンド / 本計画の唯一の正）---
make coverage-ci
# 等価な直書き:
.venv/bin/python3 -m pytest -q \
  -m "not integration and not perf and not slow and not coverage_gate" \
  --cov=src --cov-report=term-missing --timeout=180 -p no:cacheprovider

# --- JSON 出力を伴う測定（フロア検査の入力 / Step 1a と同等）---
.venv/bin/python3 -m pytest -q \
  -m "not integration and not perf and not slow and not coverage_gate" \
  --cov=src --cov-report=json:coverage.json --cov-fail-under=75 --timeout=180 -p no:cacheprovider

# --- フロア・総合の検査（測定しない・数秒 / Step 1b と同等）---
COVERAGE_JSON=coverage.json .venv/bin/python3 -m pytest -m coverage_gate \
  tests/regression/test_coverage_budget.py -q --timeout=300

# --- carve-out 台帳の検査（coverage_gate ではない・測定不要）---
.venv/bin/python3 -m pytest tests/regression/test_coverage_carveout_registry.py -q --timeout=300

# --- 上記をまとめて実行する正規の入口 ---
make verify-coverage

# --- 閾値の確認（pytest を起動せず設定だけ読む）---
.venv/bin/python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['tool']['coverage']['report']['fail_under'])"

# --- 総レポート（TOTAL 行 = fail_under が比較する値）---
.venv/bin/python3 -m coverage report | tail -3

# --- 全体の非回帰確認 ---
.venv/bin/python3 -m pytest tests/unit -q --timeout=120 -p no:cacheprovider
.venv/bin/python3 -m pytest tests/regression -m "not coverage_gate" -q --timeout=300 -p no:cacheprovider
```

---

## 9. 工数見積と将来項

| Step | 見積 | コミット数（目安） |
|---|---:|---:|
| 0 計測一元化 | 0.5 日 | 2 |
| 1 閾値 75 + budget テスト | 0.5 日 | 2（CI 初回実測の待ちを含む） |
| 2 carve-out 台帳 | 1 日 | 3 |
| 3 stale + `__init__` 監査・移設 | 1〜2 日 | 3〜5 |
| 4 パッケージ別フロア | 1 日 | 2 |
| 5 backend ラウンド | 3〜4 日 | 8〜12 |
| 6 小規模 4 パッケージ | 2 日 | 4〜6 |
| 7 分岐カバレッジ | 3 日 | 6〜8 |
| 8 ドキュメント整合 | 0.5 日 | 1 |
| **合計** | **12.5〜15.5 日** | **31〜41** |

**将来項（本計画の非目標だが、実測から次にやるべきことが分かる）**:

1. **`fail_under` を 77 へ**（Step 7 到達後の実測に応じて）。閾値と実測の乖離を 1pt 台に保つ。
2. **分岐単独フロアの引き上げ**（現状 branch-only 67.73% は行 80.92% と 13pt 開く。
   Step 7 で 72% を作るまでは放置扱い）。
3. **`backend` を 75 へ**（+7.24pt の余地が最大。本計画では 70 まで）。
4. **統合テストのカバレッジ**（別計画のゲート化と同時に、統合込みの閾値を別立て定義）。
5. **フロントエンド `thresholds: 50`**（別バイナリ・別計画）。

---

## 10. 完了の定義（Definition of Done for PLAN_D）

- [ ] `pyproject.toml` の `fail_under = 75`
- [ ] CI `.github/workflows/ci.yml` の `--cov-fail-under=75`
- [ ] `make coverage-ci` が存在し、CI と**同一コマンド**（r5 のテストが担保）
- [ ] `make verify-coverage`（測定 1 回 → 総合・フロア検査）が存在し、
      `pytest.ini` に `coverage_gate` マーカーが登録され、
      **測定実行のスコープに `not coverage_gate` が含まれる**
- [ ] `make test-unit` はカバレッジを測らない
- [ ] `tests/regression/test_coverage_budget.py` が
      (a) 閾値の 2 箇所一致、(b) `fail_under >= 75`、(c) スコープ一致（`coverage_gate` 除外含む）、
      (d) 総合実測 ≥ `MEASURED_FLOOR`、(e) パッケージ別フロア を担保
- [ ] `tests/regression/test_coverage_carveout_registry.py` が r1〜r4 を担保
- [ ] `config/coverage_carveout_registry.json` に全 carve-out が**理由付き**で台帳化
- [ ] `config/coverage_floors.json` に全 35 パッケージのフロアが CI 実測ベースで存在
- [ ] `src/schemas/easy_mode.py` の stale omit が削除済み
- [ ] `__init__.py` ロジック含有 46 件が台帳化され、非 shim 14 件の `action` が決定・実行済み
- [ ] `pragma: no cover` 27 箇所すべてに理由コメント
- [ ] `docs/TEST_STRATEGY.md` の「55% → 65% → 75%」が実績と一致
- [ ] `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md` の閾値記述が 75
- [ ] `tests/regression/` の既知失敗が 8 件を超えていない
