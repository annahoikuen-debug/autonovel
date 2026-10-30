# AutoNovel 残タスク＋継続改善 統合整改計画書【J1 / 36 ステップ】

## ── 「改善案1〜3の完了」から「本番品質の定着」まで ──

- **文書ID**: `PLAN_J1_REMAINING_36STEPS`
- **作成日**: 2026-10-30
- **起点**: 改善案1（シークレット強化）・2（設定SSOT化）・3（4層設計＋境界強制）の完了時点
- **対象**: AutoNovel v6.0.0 / HEAD `5f6fe36` 以降
- **総合状態**: 改善案1・2 完了（`70fe74a`）／改善案3 計画フェーズ完了（`5f6fe36`）／**実移行と改善案4〜9 は未着手**
- **構成**:
  **TRACK-W（環境・WIP修復）= 6** ／ **TRACK-A（4層実移行）= 10** ／ **TRACK-Q（テスト品質）= 5** ／
  **TRACK-S（静的解析）= 4** ／ **TRACK-N（NSFW分離）= 4** ／ **TRACK-C（LLMコスト）= 3** ／
  **TRACK-R（リリース衛生）= 4** ＝ **計 36 ステップ**

---

## 0. 位置づけ

先行の改善案1〜3で「セキュリティの土台」「設定のSSOT」「4層アーキテクチャの設計図と境界チェック」を確立した。
本書はそこから先の**残タスク（47ファイルの未コミットWIP・4層の実移行）**と**今後の改善（テスト品質・静的解析・NSFW分離・コスト・リリース衛生）**を、
**各ステップが独立して revert できる 36 の小さな単位**に分割した実行計画である。

| 系統 | 対象（元の改善案） | 完了条件 |
|---|---|---|
| TRACK-W | 環境・WIP修復（前提） | `pytest` が環境起因で落ちなくなり、47 WIP が triage 済み |
| TRACK-A | 改善案3 実移行（F1〜F3 節） | 契約2 の ratchet が 44→0 近傍へ縮小 |
| TRACK-Q | 改善案4 テスト品質 | coverage gate 40→60%、flaky 0 |
| TRACK-S | 改善案5 静的解析 | lint ratchet ベースライン縮小、format ゲート昇格 |
| TRACK-N | 改善案6 NSFW分離 | 官能モジュールを分離・opt-in 化、規制チェック追加 |
| TRACK-C | 改善案7 LLMコスト | 1話の LLM 呼出 10→6 回、コストKPIをPrometheus化 |
| TRACK-R | 改善案8・9 デプロイ/バージョン | 起動エントリ統一、CHANGELOG自動化 |

**唯一のゴールは「土台を固めた上で、壊れないまま少しずつ良くする」。** 各ステップは修正とリグレッションテストを同一コミットで完結させる。

---

## 0.1 分割原則（先行計画 H1 に準拠）

| # | 原則 | 内容 |
|:---|:---|:---|
| **P1** | ファイル排他所有 | 各ステップの「変更」に列挙されたファイルのみ触る |
| **P2** | 完了判定は1行 | 「テストが緑か赤か」「境界チェックが exit 0 か」だけを見る |
| **P3** | 修正とテストは同一コミット | リグレッションテストの無い修正を残さない |
| **P4** | 反証テストは赤を確認 | 修正前にそのテストが**実際に赤くなる**ことを確認する。**赤を確認できないテストは書かない** |
| **P5** | 猜測禁止 | 行番号・関数名は編集前に `grep`/`Get-Content` で実地確認する |
| **P6** | 1ステップ = 1コミット | 失敗したら `git reset --hard HEAD~1` して次へ |
| **P7** | 環境隔離 | 並行 pytest は `DATABASE_URL` を分ける |
| **P8** | 粒度 | 1ステップ ≒ 30分以内 |
| **P9** | 判断ゼロ | 曖昧さは本書で先回り。表に無い判断は ESR（§0.4） |
| **P10** | コピペ原則 | コマンドはそのまま実行できる完全形で書く |
| **P11** | ロールバック可用 | 既存テストの改変を必須にせず、新規テストで完結 |
| **P12** | Deviation記録 | 本書と異なる実行をしたなら PR 本文に理由を1行 |

### P4 の実行手順（全ステップ共通・省略不可）
1. 新規リグレッションテストを書く
2. `pytest <該当> -q` で**赤**になることを確認（まだ修正していないから赤であるべき）
3. 修正する
4. `pytest <該当> -q` で**緑**になることを確認
5. コミット

### 0.2 環境の前提（TRACK-W 完了まで必読）
現時点でテストが落ちる原因の大半は**環境依存**である（コード缺陷ではない）。
- `ModuleNotFoundError: No module named 'asyncpg'` / `'psycopg'` → DBドライバ未インストール
- `create_access_token() got an unexpected keyword argument 'data'` → `jwt.py` のシグネチャ変更（`user_id=`）に対し `test_auth_real_session.py` が旧 `data=` API を使うWIPの不整合

### 0.3 決定表（曖昧さの先回り）

| 論点 | 決定 |
|---|---|
| 4層移行の順序 | 依存の浅い順（domain → application → infrastructure → interfaces）。各フェーズで境界チェックが緑を保つこと |
| 未コミット47 WIP の扱 | TRACK-W で1件ずつ triage（commit / revert / WIP継続）。**本計画はWIPを勝手に捨てない** |
| coverage gate | 40% → 60%（TRACK-Q）。80%は将来フェーズ |
| NSFW モジュール | コアから分離し `ENABLE_NSFW` opt-in。既定無効 |
| LLM コスト目標 | 1話10回 → 6回（監査5→2）。完全4-5回は追加最適化で |

### 0.4 ESR（Escalation）
本書に記載のない判断・想定外の障害は、**当該ステップをスキップして記録**し、TRACK終端の retro に回す。推測で編集しない。

---

## TRACK-W：環境・WIP修復（6ステップ・全TRACKの前提）

> 目的: テストが環境起因で落ちない状態にし、47の未コミットWIPを triage する。
> これが終わらないと TRACK-A 以降の「緑の検証」ができない。

### W1. DBドライバを dev 依存に追加（asyncpg/psycopg）
- **目的**: `test_backend_database_core.py` の `ModuleNotFoundError` を解消
- **変更**: `pyproject.toml` の `dev` extra に `asyncpg` `psycopg[binary]` を追加（`dependencies` には既に asyncpg があるが、テスト環境の venv に未投入）
- **リグレッションテスト**: `tests/unit/backend/test_db_drivers_available.py`（新規）— `import asyncpg` / `import psycopg` が成功することを assert（欠ければ即 fail で環境未整備を検出）
- **完了条件**: `pytest tests/unit/backend/test_backend_database_core.py -q` が `ModuleNotFoundError` で落ちなくなる

### W2. jwt シグネチャ不整合の triage
- **目的**: `create_access_token(data=)` vs `(user_id=)` の WIP 不整合を解消
- **変更**: `src/backend/security/jwt.py`（WIP・`user_id=` が正）／`tests/unit/backend/test_auth_real_session.py`（旧 `data=` を使う箇所を `user_id=` + `role=` へ）
- **リグレッションテスト**: `tests/unit/security/test_jwt_signature_contract.py`（新規）— `create_access_token` / `create_refresh_token` の公開シグネチャ（`user_id`, `role`, `extra_claims`）を固定し、将来の引数改名を検出
- **完了条件**: `pytest tests/unit/backend/test_auth_real_session.py -q` が緑

### W3. WIP 47ファイルの triage 表作成
- **目的**: どの WIP を commit / revert / 継続するかを決める表を作る（勝手に捨てない）
- **変更**: `docs/plans/WIP_TRIAGE.md`（新規）— `git status --short` の47件を「改善案1-3と関連／無関係の機能WIP／削除予定」に分類
- **リグレッションテスト**: なし（文書）。ただし表の各行に「テスト状態（緑/赤/環境起因）」を必須記載
- **完了条件**: 47件すべてがいずれかのカテゴリに分類済み

### W4. 無関係WIPのコミット（機能として成立するもの）
- **目的**: 改善案と無関係だが自立して緑の WIP を commit して土台を締める
- **変更**: triage 表で「commit」に分類したファイル群（frontend・`multimedia` など個別コミット）
- **リグレッションテスト**: 各コミット前に対象領域のテストが緑であることを確認（新規テスト不要・既存利用）
- **完了条件**: triage 表の「commit」栏が空になる

### W5. 動作しない/削除予定WIPの revert
- **目的**: 破損した WIP（例: `credit_guard.py` 削除の影響）を整理
- **変更**: triage 表で「revert」分類のファイルを `git checkout --` / `git rm` で解消。`credit_guard.py` 削除が他に影響しないか `grep` で確認
- **リグレッションテスト**: `grep -rn "credit_guard" src tests` が空（残存参照のないことを保証するアサーションを `tests/unit/security/test_no_dead_references.py` に追加）
- **完了条件**: `git status --short` が改善案関連のみ（理想0）／残は「WIP継続」分のみ

### W6. テストスイートの速度改善（フィクスチャ調査）
- **目的**: フル3時間超を短縮し、TRACK-A 以降の検証を現実的にする
- **変更**: `tests/conftest.py` の重い import/フィクスチャを調査。`pytest-timeout` を活用しハング検出。`-p no:randomly` 既定化を検討
- **リグレッションテスト**: `pytest --collect-only -q | tail` が30秒以内に収まることを CI で確認（収集速度の劣化を検出）
- **完了条件**: `tests/unit` の実行時間が显著に短縮（目標: 現状の1/3）

---

## TRACK-A：4層アーキテクチャ実移行（10ステップ）

> 目的: 改善案3の設計（`docs/architecture/layers.md`）を実際に移行する。
> 各ステップ後に必ず `python scripts/check_layer_boundaries.py` を実行し、契約1が緑・契約2が縮小していることを確認する。
> 基盤: 契約2 ベースライン `domain:4 / application:1 / infrastructure:39`（計44）を 0 へ縮小する。

### A1. domain の自律化: writing/coordinator の agents/services 依存を port 経由に
- **目的**: 契約2 の `domain:4` を解消（`domain/writing/coordinator.py` が `agents`/`services` を依存）
- **変更**: `src/domain/writing/coordinator.py` — 外部依存を `src/application/ports/` の port 経由の DI に置換（コンストラクタ引数化）
- **リグレッションテスト**: `tests/unit/domain/test_writing_coordinator_no_legacy_import.py`（新規）— coordinator モジュールが `src.agents`/`src.services` を import しないことを AST で assert
- **完了条件**: 上テストが緑 ＋ `check_layer_boundaries.py --report` の domain が 4→0

### A2. domain の自律化: writing/quality_loop の同様解消
- **目的**: 残る domain の agents/services 依存を解消
- **変更**: `src/domain/writing/quality_loop.py` — port 経由 DI へ
- **リグレッションテスト**: `tests/unit/domain/test_quality_loop_no_legacy_import.py`（新規）— 同上の AST アサーション
- **完了条件**: domain の契約2 が 0（A1+A2）

### A3. application の自律化: book_use_cases の backend 依存を port 化
- **目的**: 契約2 の `application:1` を解消
- **変更**: `src/application/use_cases/book_use_cases.py` — `src.backend` 参照を port に置換
- **リグレッションテスト**: `tests/unit/application/test_book_use_cases_no_backend.py`（新規）— backend を import しない AST アサーション
- **完了条件**: application の契約2 が 0

### A4. infrastructure: DB マッパの backend 依存解消（book_mapper）
- **目的**: 契約2 の `infrastructure:39` のうち `backend`(DB) 依存を解消する第一歩
- **変更**: `src/infrastructure/database/mappers/book_mapper.py` — ORM 参照を `src/infrastructure/database/models/` 内に閉じる（backend/database から infrastructure/database へ実体移動）
- **リグレッションテスト**: `tests/unit/infrastructure/test_book_mapper_no_backend.py`（新規）— backend import なしの AST アサーション
- **完了条件**: 該当ファイルの backend import が消える

### A5. infrastructure: ORM モデルの一元化（backend/database/models → infrastructure/database/models）
- **目的**: infrastructure の `backend` 依存の大多数（repositories/*）を一掃する基盤
- **変更**: ORM 実体を `src/infrastructure/database/models/` へ移し、`src/backend/database/models.py` を互換再エクスポート shim に（Q3=B 方針）
- **リグレッションテスト**: `tests/regression/test_orm_import_paths.py`（新規）— 旧 `src.backend.database.models` 経由の import が引き続き機能すること（shim の後方互換）を assert
- **完了条件**: `check_layer_boundaries.py --report` の infrastructure が大幅減（39→10 以下）

### A6. infrastructure: repositories/* の backend/services 依存を model shim 経由へ
- **目的**: 残る repositories の依存を断線
- **変更**: `src/infrastructure/repositories/*.py` — A5 の shim を経由して ORM を参照（backend 直 import を除去）
- **リグレッションテスト**: `tests/unit/infrastructure/test_repositories_no_backend.py`（新規）— repositories が backend/services を import しない AST アサーション
- **完了条件**: infrastructure の契約2 が 0 近傍（≤5）

### A7. infrastructure: external/anthropic_client の services 依存解消
- **目的**: LLM adapter を infrastructure に自己完結させる
- **変更**: `src/infrastructure/external/anthropic_client.py` — `src.services` 参照をローカル化
- **リグレッションテスト**: `tests/unit/infrastructure/test_anthropic_client_no_services.py`（新規）
- **完了条件**: 該当ファイルの services import が消える

### A8. interfaces: backend/routers → interfaces/api への移設（第一段階）
- **目的**: 最外層を整備する。まず依存の薄いルーターから
- **変更**: `src/backend/routers/` のうち DB 直結の薄いものを `src/interfaces/api/` へ移設し、旧パスを shim で維持
- **リグレッションテスト**: `tests/contract/test_router_paths.py`（新規）— 旧 import 経路（`src.backend.routers.*`）が OpenAPI に同じパスを提供し続けること（契約不変）を assert
- **完了条件**: 移設したルーターで API 契約テストが緑

### A9. interfaces: server.py の bootstrap 分離
- **目的**: `src/backend/server.py`（WIP混在）を「起動 bootstrap」と「ルーター登録」に分離
- **変更**: 起動ロジックを `src/interfaces/api/app_factory.py` へ、`server.py` は互換エントリに
- **リグレッションテスト**: `tests/regression/test_server_entrypoint.py`（新規）— `src.backend.server:app` が引き続き FastAPI インスタンスを提供（uvicorn 起動経路の不変）を assert
- **完了条件**: `uvicorn src.backend.server:app` が従来どおり起動

### A10. 契約2ベースラインの更新と retro
- **目的**: TRACK-A の縮小をベースラインに反映し、残タスクを明文化
- **変更**: `python scripts/check_layer_boundaries.py --update-baseline`（縮小後の値を記録）、`docs/architecture/layers.md` §6 を更新
- **リグレッションテスト**: なし（ベースライン更新）。`check_layer_boundaries.py` が exit 0 であることを確認
- **完了条件**: 契約2 が 44 から大幅縮小（目標 ≤10）で境界チェック緑

---

## TRACK-Q：テスト品質・カバレッジ（5ステップ・改善案4）

### Q1. flaky テストの棚卸しと分離
- **目的**: `artifacts/flaky_tests.json` の中身を精査し、修正または削除
- **変更**: `artifacts/flaky_tests.json`・該当テスト。再現しないものは削除、するものは `@pytest.mark.flaky` で隔離
- **リグレッションテスト**: flaky 一覧の各テストを 3 回連続実行し同一結果になることを CI で確認する仕組み（`scripts/check_flaky.py` 新規）
- **完了条件**: flaky リストが空、または全て `@pytest.mark.flaky` で隔離済み

### Q2. テスト除外リストの縮小（omit_list）
- **目的**: `artifacts/omit_list.txt` / `omit_matched_files.txt` の「除外して隠す」運用を廃止
- **変更**: 除外されたテストを1件ずつ再有効化。`pyproject.toml` の coverage `omit`（`src/services/age_client.py` 等の非推奨スタブ）を再点検
- **リグレッションテスト**: 再有効化した各テストが緑であることを確認（新規不要・既存利用）
- **完了条件**: `omit_list.txt` が縮小または空

### Q3. coverage gate の引き上げ（40→50%）
- **目的**: 段階的に品質閾値を上げる
- **変更**: `Makefile` の `test-unit` の `--cov-fail-under=40` → `50`
- **リグレッションテスト**: `make test-unit` が 50% を満たして緑であることを確認
- **完了条件**: gate 50% で緑

### Q4. coverage gate の引き上げ（50→60%）
- **目的**: 目標の 60% へ
- **変更**: `Makefile` の `--cov-fail-under` → `60`。不足分は優先モジュール（`src/domain` `src/application`）にテストを追加
- **リグレッションテスト**: 追加した各テストが対象モジュールの未カバー行を埋めることを `--cov-report=term-missing` で確認
- **完了条件**: gate 60% で緑

### Q5. 契約テストの拡充（OpenAPI スナップショト）
- **目的**: API の破壊的変更を CI で検出
- **変更**: `tests/contract/` に主要ルーターの OpenAPI スナップショトを追加・整備
- **リグレッションテスト**: 意図的に1エンドポイントのレスポンススキーマを変更し、契約テストが**赤**になることを確認（P4）
- **完了条件**: `make test-contract` が API 変更を検出できる

---

## TRACK-S：静的解析ゲート強化（4ステップ・改善案5）

### S1. ruff ベースラインの縮小開始（F401 の意図的 import 整理）
- **目的**: `config/ci_lint_baseline.json` の ruff エラー数を下げる
- **変更**: `__init__.py` 以外の未使用 import（F401）を人目で分類し、非公開のものだけ削除
- **リグレッションテスト**: 削除した import を使っている箇所が無いことを `grep`＋既存テストの緑で確認
- **完了条件**: `python scripts/ci_lint_ratchet.py --tool ruff` がベースラインより減少を報告

### S2. ruff ベースライン縮小（F841 未使用変数）
- **目的**: 未使用変数（F841）を整理
- **変更**: 該当箇所を削除または `_` 接頭辞化
- **リグレッションテスト**: 既存テストの緑（挙動不変）
- **完了条件**: ruff ベースラインさらに減少

### S3. mypy エラーの計画的削減
- **目的**: `mypy` の記録onlyを段階的に実効化へ
- **変更**: `src/domain` `src/application`（4層の中核）の mypy エラーを優先解消。`config/ci_lint_baseline.json` の `mypy_errors` を下げる
- **リグレッションテスト**: 対象モジュールの `mypy src/domain src/application` がエラー0であることを確認
- **完了条件**: mypy ベースライン減少

### S4. `ruff format --check` のゲート昇格検討
- **目的**: format を record-only から blocking へ
- **変更**: `Makefile` の `verify` に `format-check` が既にあるが、CI（`.github/workflows/ci.yml`）で blocking 化
- **リグレッションテスト**: format が必要なファイルを1つ作り、CI が**赤**になることを確認（P4）
- **完了条件**: CI が format 違反で fail する

---

## TRACK-N：NSFW分離・ガードレール（4ステップ・改善案6）

### N1. 官能モジュールの所在棚卸し
- **目的**: `config/erotic_*.py`（8ファイル）の参照元を全て洗い出す
- **変更**: `docs/plans/NSFW_INVENTORY.md`（新規）— 各 erotic_* の import 元と有効化経路を表化
- **リグレッションテスト**: なし（棚卸し）。ただし表の各行に「有効化フラグ」を必須記載
- **完了条件**: 8ファイルの参照元が全て特定済み

### N2. 官能モジュールの分離（`src/nsfw/` へ移設）
- **目的**: コアから官能生成機能を隔離
- **変更**: `config/erotic_*.py` → `src/nsfw/` へ移設、旧パスを shim で維持（Q3=B）
- **リグレッションテスト**: `tests/unit/nsfw/test_nsfw_isolated.py`（新規）— `ENABLE_NSFW` 無効時に官能語彙バンクが**ロードされない**ことを AST/遅延import で assert
- **完了条件**: 上テストが緑

### N3. `ENABLE_NSFW` オプトインの強制
- **目的**: デフォルト無効・明示 opt-in なしに官能出力をさせない
- **変更**: `src/backend/config.py` に `ENABLE_NSFW: bool = False` を追加し、官能生成経路の入口でチェック
- **リグレッションテスト**: `tests/regression/test_nsfw_opt_in.py`（新規）— `ENABLE_NSFW=false` で官能生成経路が拒否されることを assert
- **完了条件**: 上テストが緑

### N4. 出力形式へのコンテンツポリシーチェック
- **目的**: なろう・カクヨム・EPUB への規制違反表現の自動ブロック
- **変更**: エクスポート部（`formatters/` or `src/easy_mode/phase3/`）にポリシーチェックを追加
- **リグレッションテスト**: `tests/unit/export/test_content_policy_gate.py`（新規）— 違反表現のサンプルZIPが書き出しでブロックされることを assert（P4 で赤→緑）
- **完了条件**: 上テストが緑

---

## TRACK-C：LLMコスト最適化（3ステップ・改善案7）

### C1. 監査フェーズの LLM 呼出を KPI 化
- **目的**: 1話あたりの呼出回数を可視化（現状10回・うち監査5回）
- **変更**: Prometheus メトリクスに `llm_calls_per_episode` / `llm_calls_audit_phase` を追加
- **リグレッションテスト**: `tests/unit/observability/test_llm_cost_metrics.py`（新規）— 監査呼び出しがメトリクスに記録されることを assert
- **完了条件**: メトリクスが `/metrics` に出力される

### C2. 監査モデルの階層化（簡易判定を安価モデルへ）
- **目的**: 5監査のうち機械的判定（事実性・構造）を tier1 安価モデルへ
- **変更**: `OPENROUTER_ROUTING` / モデル割当を、監査の内訳に応じて設定
- **リグレッションテスト**: `tests/unit/llm/test_audit_tier_routing.py`（新規）— 事実性監査が安価 tier にルーティングされることを assert
- **完了条件**: `scripts/report_episode_cost.py` で1話のコスト低下を確認（目標 10→6 回）

### C3. オーディター結果のキャッシュ導入
- **目的**: 同一原稿ハッシュの再監査をスキップ
- **変更**: 監査結果を原稿ハッシュでキャッシュ（`semantic_cache` or 新規）
- **リグレッションテスト**: `tests/regression/test_audit_cache_reuse.py`（新規）— 同一原稿で2回目の監査が LLM 呼出0になることを assert
- **完了条件**: 上テストが緑

---

## TRACK-R：リリース衛生・デプロイ・バージョン（4ステップ・改善案8・9）

### R1. 起動エントリの一本化方針策定と bat の非推奨化
- **目的**: `アプリ起動.bat` 等の Windows 特化スクリプトを `start_local.ps1` へ一本化
- **変更**: 各 bat に非推奨バナーを追加し、README を `scripts/start_local.ps1` 中心へ
- **リグレッションテスト**: `tests/regression/test_startup_docs_consistent.py`（新規）— README の起動手順が `start_local.ps1` を参照していることを assert（文書の陳腐化を検出）
- **完了条件**: bat に非推ワナー、README 整合

### R2. ルート直下の `.db` ファイル整理
- **目的**: `a.db` `test.db` `autonovel.db` 等の散在を `storage/` へ集約
- **変更**: `.gitignore` にルート `.db` を追加、`Makefile` の `clean` 対象に `a.db` `test.db` を追加
- **リグレッションテスト**: `tests/regression/test_no_db_in_root.py`（新規）— ルート直下に追跡中 `.db` が無いことを assert
- **完了条件**: `git ls-files '*.db'` が `storage/` 配下のみ

### R3. バージョン SSOT の統一（.env.example の v5.2.1 表記）
- **目的**: `.env.example` ヘッダーの `v5.2.1` を `pyproject.toml` に追随
- **変更**: `.env.example` のヘッダーをバージョン固定せず「pyproject.toml 参照」表記へ
- **リグレッションテスト**: `tests/regression/test_v5_version_consistency.py` に `.env.example` のバージョン表記が pyproject と矛盾しないことを追加
- **完了条件**: 既存バージョン一貫テストが `.env.example` も検証して緑

### R4. CHANGELOG 自動化の導入
- **目的**: Conventional Commits から CHANGELOG を自動生成
- **変更**: `scripts/generate_changelog.py`（新規）または GitHub Actions。既存コミット（`feat(security)` 等）を解析して CHANGELOG.md を生成
- **リグレッションテスト**: `tests/regression/test_changelog_covers_releases.py`（新規）— 直近リリースタグが CHANGELOG に存在することを assert
- **完了条件**: `CHANGELOG.md` が自動生成され一貫テキスト

---

## 1. 完了の定義（全体）

| トラック | 完了条件 |
|---|---|
| W | テストが環境起因で落ちず、47 WIP が triage 済み |
| A | `check_layer_boundaries.py` の契約2 が ≤10（理想0）で境界チェック緑 |
| Q | coverage gate 60% で緑、flaky 0、契約テストが API 変更を検出 |
| S | ruff/mypy ベースライン縮小、format が CI で blocking |
| N | 官能モジュール分離・opt-in 化・出力ポリシー導入 |
| C | 1話の LLM 呼出 10→6 回、コストKPI可視化 |
| R | 起動一本化・DB散在解消・バージョン/CHANGELOG 自動化 |

## 2. リグレッション防止の横断原則

1. **AST 境界アサーション**: TRACK-A の各ステップは「当該モジュールが旧レイヤーを import しない」を AST で固定（`check_layer_boundaries.py` と同じ検査をテスト内に閉じ込める）。
2. **後方互換 shim の契約テスト**: 移設した全モジュールに、旧 import 経路が引き続き機能するテストを1本ずつ置く（Q3=B 方針の safety net）。
3. **赤→緑の強制（P4）**: 破壊的検出（コンテンツポリシー・契約・メトリクス）は、修正前に赤になることを必ず確認する。
4. **数値 KPI の閾値固定**: LLM コスト・coverage・ratchet は全て CI の閾値として固定し、劣化を自動検出する。

---
*本書のパス・件数は 2026-10-30 実測（改善案1〜3 完了時点ワークツリー）。実行前に P5 に従い grep で実地確認すること。*
