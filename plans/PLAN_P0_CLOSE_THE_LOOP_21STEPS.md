# PLAN_P0: ループを閉じる — CI 復活・本番デプロイ・実 LLM 計測・フラグ判定 (21 ステップ)

- **文書ID**: `PLAN_P0_CLOSE_THE_LOOP_21STEPS`
- **作成日**: 2026-11-25
- **対象**: AutoNovel v7.0.0（HEAD `b470b5ca`、main 未 push）
- **位置づけ**: [`docs/ROADMAP_NEXT.md`](../docs/ROADMAP_NEXT.md) §5 優先度 **P0「ループを閉じる」の実行計画書**。本書は施策レベルの合意（ROADMAP_NEXT §5 P0）をステップ分解したものであり、起票時点では**承認待ち**。
- **前提**:
  - `docs/STATUS.md`（実装状況 SSOT）の記載を現状の正とする
  - フラグ判定の AB 手順は `plans/PLAN_H8F_ROLLOUT_12STEPS.md`（O6-O9）、RAG は `plans/PLAN_R5_RAG_WIRING_24STEPS.md`（F1-F3）、伏線投票は `docs/STATUS.md` §9.2（R1-④）を引き継ぐ
  - デプロイ手順は [`docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md`](../docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md) を SSOT とし、本書は重複記載しない
- **原則**: `plans/PLAN_J1_REMAINING_36STEPS.md` §0.1 の分割原則（P1〜P12）を継承する。特に **P4（反証確認）・P5（推測禁止・実地 grep）・P6（1ステップ=1コミット）・P12（Deviation 記録）** を厳守する。

---

## 0. TL;DR

コードの品質管理は十分である。次のボトルネックは「作った機能が価値を出しているかを測るループ」であり、本計画はそのループを 4 つの TRACK で閉じる。

| # | TRACK | 目的 | 出口ゲート |
|:---|:---|:---|:---|
| **A** | CI 復活（5 ステップ） | push で GitHub Actions が発火し全 job 緑 | G1: check runs ≥ 1 かつ全 job 緑 |
| **B** | 本番デプロイ（6 ステップ） | 計測可能な本番 1 環境を立ち上げ E2E 完走 | G2: `/health/ready` 200 + 登録→生成→ZIP 完走 |
| **C** | 実 LLM 生成・KPI 実測（6 ステップ） | `book_count > 0` にし KPI を実測値で埋める | G3: KPI 実測表が `docs/STATUS.md` に記録済み |
| **D** | フラグ ON/OFF 判定（4 ステップ） | H8 / RAG / 伏線投票の既定値を実データで決める | G4: 判定表の全項目が埋まり P1 が解禁 |

**最重要契約（R1 原則）**: フラグの ON 化は「実測による改善証明」が前提。判定を通過しなければ**既定 OFF 維持**とし、その根拠を `docs/STATUS.md` に文書化する。OFF 維持は「失敗」ではなく「安全側の決定」である。

---

## 1. 現状の正確な記録（2026-11-25 実査）

### 1.1 CI（`.github/workflows/ci.yml`）— **2026-11-26 実測で更新**

| 項目 | 実測（2026-11-26、GitHub REST API による無認証読み取り） |
|:---|:---|
| トリガー | push(main, develop) / PR(main, develop)。concurrency group あり |
| jobs | `static-analysis` / `release-consistency` / `test` / `integration` / `frontend` の 5 本 |
| YAML 構文 | Q7（2026-11-24）で修復済み（`72d87e3d` で混入した壊れを修正・`tests/regression/test_workflow_syntax.py` で回帰検出） |
| workflow 登録 | `ci.yml` は GitHub に **`state: active` で登録済み**（created 2026-10-03 / updated 2026-11-23）。6 workflows すべて active |
| **発火状況** | **main ブランチの workflow runs は total_count = 0。** リポジトリ全体の runs は 32 件で、**最新の発火はすべて `lp.yml` × `feature/commercial-lp-phase1`・最終 2026-11-03 16:38（conclusion: failure）**。つまり **Actions 全体が 2026-11-03 以降 1 件も発火していない** |
| 原因の絞り込み | workflow ファイル側は解消済み（active 登録）。不発の原因は**リポジトリ/アカウント設定レベル**（fork 由来リポジトリでの Actions 無効化 or Billing 等を推定）。settings API（`/actions/permissions`）は認証必須（401 実測）のため、**ユーザー側確認（A2）が必須** |
| push 状況 | `b470b5ca` 以降、並行作業の `8ddfe522`（挿絵 Increment 1）・`fa88fe1a`（ドキュメント）まで push 済み（`ls-remote` 確認）。**push は届いているのに発火しない** |
| Python バージョン | CI は `.python-version`（3.12）。ローカル venv は 3.13.5 で mypy 実測件数が異なる（**実測**はローカル約 323 のみ）。`docs/STATUS.md` §4 の「CI 3.12 で 388」は 2026-11-15 記録だが、main で runs=0 のため **CI 実測は存在しない（予測値として扱う）**。ratchet baseline 450 は pass 見込み |

> **A5 の矛盾解消（2026-11-26）**: `CHANGELOG.md` Q7 の「CI 復活」は **誤り** であったことが確定
> （YAML 修復は事実だが、発火は復活していない）。`docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §7 の
> 記載が正しかった。本計画 TRACK-A の残りは A2（ユーザー側設定確認）のみ。

### 1.2 デプロイ（`docker-compose.prod.yml`）

| 項目 | 実測 |
|:---|:---|
| 起動コマンド | `make prod-up`（= `docker compose -f docker-compose.prod.yml up -d --build`） |
| 必須環境変数（fail-fast） | `JWT_SECRET_KEY` / `ALLOWED_API_KEYS` / `CORS_ORIGINS` / `POSTGRES_PASSWORD` / `REDIS_PASSWORD` |
| Stripe | 本番起動時、`STRIPE_WEBHOOK_SECRET` 未設定かつ `ALLOW_UNSIGNED_WEBHOOKS=true` でもないと拒否される。**計測環境では値を設定すれば起動は通る（決済疎通は本計画の対象外）** |
| 公開ポート | frontend の `8080` のみ。backend は expose のみ（nginx が `/api` `/easy_mode` `/health` `/metrics` をリバースプロキシ） |
| マイグレーション | backend コンテナ 1 台のみ実行。worker は `SKIP_ALEMBIC=1` |
| ヘルス | `/health/live` / `/health/ready` / `/health/detail`（`src/backend/routers/health.py`） |
| ドキュメント | `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md`（§7 デプロイ手順 / §8 ロールバック） |

### 1.3 生成・計測に使う既存資産

| 資産 | 実体 | 用途 |
|:---|:---|:---|
| easy mode 生成 | `POST /easy_mode/generate`（`src/backend/routers/easy_mode.py:352`）。payload に `target_episodes` / `spine_quality`（既定 `off`） | TRACK-C の 20 話生成。非同期タスクで `GET /easy_mode/status/{task_id}` で進捗取得 |
| LLM プロバイダ | `LLM_PROVIDER`（mock / openai / gemini / claude / ollama / vllm）。変更後は **API と Huey ワーカー両方の再起動**が必要 | TRACK-C で実プロバイダに切替 |
| コスト計測 | Prometheus `llm_api_tokens_total{model, token_type}`（`src/backend/observability/metrics.py:59`）+ `scripts/report_episode_cost.py --db <sqlite> --json` | TRACK-C のコスト実測 |
| 構成実測 | `scripts/measure_spine_alignment.py --json`（DB 内の Plot テーブル対象。`book_count = 0` が現状） | K1-K3 の実書籍値を差し替え |
| 伏線 KPI | `GET /api/graph/foreshadowing/kpi?book_id=&current_episode=`（`src/backend/routers/graph.py:353`）+ `foreshadowing_*` メトリクス | 回収率・解決率の実測 |
| 伏線投票集計 | `python -m scripts.analyze_foreshadow_vote_agreement` | TRACK-D D3 の一致率算出 |
| AB データセット置場 | `var/ab_datasets/`（H8F O6 の前例。**コミット対象外**） | TRACK-D のデータセット |

### 1.4 フラグ判定の対象（既定 OFF のまま眠っている主要改善）

| フラグ群 | 判定手順の出典 | 前回判定（合成データ） |
|:---|:---|:---|
| `ENABLE_AUDIT_QUOTE_PATCH` / `ENABLE_AUDIT_LESSONS` | H8F O7/O8/O9 | 採用率 87%・破壊 0 だが再合格率・コスト未測定 → **既定 OFF 維持**（`docs/STATUS.md` §11） |
| RAG 注入（HyDE / BM25/RRF / リランカー） | R5 F1-F3 | 実装完了・フラグ全 OFF でバイト同一契約。AB 未実施 |
| 伏線 LLM 第 4 投票 `ENABLE_FORESHADOW_LLM_VOTE` | STATUS §9.2 R1-④ | 未実施（shadow 記録が前提） |

---

## 2. 設計原則（本計画の拘束）

| # | 原則 | 機械的保証 |
|:---|:---|:---|
| **R1** | 判定不通なら既定 OFF 維持。根拠のない ON 化を禁止 | D4 の判定表を `docs/STATUS.md` に記録 |
| **R2** | 計測できない判断はしない。先に計測基盤（CI→デプロイ→実生成）を整える | G1→G2→G3 の順次解禁 |
| **R3** | ユーザー側作業（GitHub 設定・API キー取得）とエージェント側作業を明確に分離する | 各ステップの「担当」列 |
| **R4** | 本計画での**ソースコード修正は D4（既定値変更）のみ**。CI の是正が要る場合は別計画に分離（ESR） | 変更ファイル一覧 |
| **R5** | 挿絵 WIP（並行作業の変更）には**一切触れない** | `git status` で常時確認 |
| **R6** | 実費が発生する生成（TRACK-C/D）は**事前に本数と上限を宣言**してから走らせる | §8 の本数表 |

> **記号の注意（review-loop Round 1 指摘 #5）**: J1 §0.1 の分割原則は **P1〜P12**、本計画 §2 のローカル原則は **R1〜R6**。
> 本文中の「（P4）」等は J1 原則、「（R4）」等は本計画 §2 原則を指す。

---

## 3. 実装ステップ（TRACK A-D / 21 ステップ）

### TRACK-A: CI 復活（A1-A5）

> **担当**: A1/A3/A4/A5 はエージェント側、A2 はリポジトリ管理者（ユーザー側）。
> `gh` CLI が無い環境ではブラウザ UI の該当画面で代替する（ESR §9）。

- **A1 現状 push と観測** — 未 push の `b470b5ca` を含む main を push し、check runs が発生するか観測する:
  ```bash
  git push origin main
  gh run list --limit 5   # または GitHub Web → Actions タブ
  ```
  完了判定: **push から 5 分以内に check runs ≥ 1 なら A4 へ。0 件なら A2 へ。**
- **A2 設定レベルの切り分け（ユーザー側）** — 以下を上から順に確認し、原因を 1 行で記録する:
  1. **Billing**: Settings → Billing → Actions の spending limit / included minutes 残量
  2. **Actions permissions**: Settings → Actions → General →「Allow all actions and reusable workflows」が選択されているか
  3. **Workflow permissions**: 同画面の「Read and write permissions」設定（release-consistency job が push 系操作を要する場合）
  4. **Organization 配下の場合**: org の Policies → Actions で repository レベルより強い制限がないか
  5. `gh api repos/{owner}/{repo}/actions/permissions` と `gh api repos/{owner}/{repo}/actions/workflows` で `ci.yml` が `state: active` か（`disabled_manually` / `disabled_inactivity` ならここが原因）
  完了判定: **原因が特定され、設定変更が完了している。**（ユーザー側作業のため本ステップはエージェントが待機）
- **A3 workflow 登録状態の確認** — A2 の後、`ci.yml` が workflow 一覧に registered かつ active であることを確認。無ければ YAML パース失敗の残存疑い → `tests/regression/test_workflow_syntax.py` をローカル実行し、YAML 側の要因を排除する。
  完了判定: **`gh workflow list` に CI が active で表示される。**
- **A4 実発火の確認** — docs コミット 1 件（または空コミット）を push し、5 本の job が起動することを確認。失敗 job が出た場合:
  - ratchet / mypy / format 系は「CI 環境（3.12）とローカル（3.13）の差」の可能性が高いため、**ローカルで 3.12 相当を再現してから**対処を判断する
  - 是正にコード変更が必要な場合は本計画を中断し、**別計画（PLAN_<ID>_CI_REMEDIATION）に分離**する（R4）
  完了判定: **check runs ≥ 1 が観測された。**
- **A5 CI 緑の確定と記録** — 全 job 緑（または既知の環境差を除き緑）であることを確認し、`docs/ROADMAP_NEXT.md` §3 課題A の CI 矛盾記述を解消する（実態を 1 行追記）。
  完了判定: **全 job 緑。`CHANGELOG.md` Q7 の記述と ROADMAP の記述の矛盾が解消済み。**

### TRACK-B: 本番デプロイ（B1-B6）

> **担当**: B1/B3/B4/B5/B6 はエージェント側（実行ホストで docker が使えること。B1 で確認）、B2 のキー発行はユーザー側。
> 手順の SSOT は `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md`。本書は完了判定のみを定める。

- **B1 実行ホストの前提確認** — `docker compose version`、ポート 8080 空き、ディスク空き容量を確認。docker が使えないホストなら本計画のデプロイ先を変更（クラウド VM 等）し Deviation として記録。
  完了判定: **`docker compose version` が動作し、8080 が空いている。**
- **B2 必須環境変数の用意（ユーザー側）** — `cp .env.example .env` のうえ、checklist §1 に従い必須 5 変数を設定:
  ```bash
  openssl rand -hex 32   # JWT_SECRET_KEY
  openssl rand -hex 16   # POSTGRES_PASSWORD / REDIS_PASSWORD
  # ALLOWED_API_KEYS / CORS_ORIGINS は実オリジンをカンマ区切りで
  ```
  計測環境では `STRIPE_WEBHOOK_SECRET` に任意のランダム値を設定して起動拒否を回避する（決済疎通は本計画の対象外）。
  完了判定: **必須 5 変数 + STRIPE_WEBHOOK_SECRET が `.env` に設定済み。**
- **B3 起動とヘルス確認** — `make prod-up` → 以下を確認:
  ```bash
  curl -f http://localhost:8080/health/live
  curl -f http://localhost:8080/health/ready
  docker compose -f docker-compose.prod.yml logs backend | grep -i alembic   # マイグレーション 1 台実行の確認
  docker compose -f docker-compose.prod.yml ps   # worker が crash-loop していないこと（SKIP_ALEMBIC=1 確認）
  ```
  完了判定: **`/health/ready` 200・worker が stable。**
- **B4 E2E 疎通** — ブラウザで `http://localhost:8080` → `/register` でユーザー登録 → かんたん執筆（`LLM_PROVIDER` はこの時点で mock でよい）→ 1 話生成 → `納品パッケージ (ZIP)` ダウンロードが完走すること。トークンなしの API 直叩きが 401 になることも確認（README 記載の認証挙動）。
  完了判定: **登録 → 生成 → ZIP 取得が完走。未認証は 401。**
- **B5 観測基盤の確認** — `http://localhost:8080/metrics` に `llm_api_tokens_total` / `foreshadowing_*` / `audit_*` が露出していることを curl で確認（H8F O3 と同型の無音性チェック: flag OFF でカウンタが増えない）。ログ出力先（`logs/` または docker logs）も記録。
  完了判定: **計測に必要なメトリクスが露出し、flag OFF で無音。**
- **B6 デプロイ記録とロールバック確認** — checklist §8 のロールバック手順（`down` → 再起動）を 1 回演習し、`docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md` に実施日と構成（ホスト・バージョン・`.env` の変数名一覧・値は記載しない）を追記。
  完了判定: **ロールバック演習済み・記録済み。→ G2 通過。**

### TRACK-C: 実 LLM 生成・KPI 実測（C1-C6）

> **担当**: C1 のキー発行はユーザー側、他はエージェント側。
> **R6**: 走らせる本数は「20 話 × 1 作品」のみ。追加本数は D で改めて宣言する。

- **C1 プロバイダ決定とキー設定** — ユーザーと相談のうえ `LLM_PROVIDER` を決定（コスト最小の tier1 系モデルを推奨。`.env` にキーを設定）。**API と Huey ワーカー両方を再起動**（既知の落とし穴 #8）。起動後、`/health/detail` の LLM チェックが緑であることを確認。
  完了判定: **実プロバイダで `/health/detail` の LLM チェックが通る。**
- **C2 20 話作品の生成** — 本番 UI（かんたん執筆）または API で `target_episodes=20`・`spine_quality` は既定（off）のまま生成。進捗は `GET /easy_mode/status/{task_id}`（または UI プログレスバー）で追跡。話単位で失敗したら既存の `retry_failed` 経路を使用し、**完走率を実測値として記録**（失敗話数も価値あるデータ）。
  完了判定: **20 話中 N 話が完走（N を記録）。`book_count = 1` 以上。**
- **C3 構成品質の実測** — 以下を実行し結果を記録:
  ```bash
  DATABASE_URL=<本番DB> python scripts/measure_spine_alignment.py --json   # K1-K3 実測
  # 監査スコア: GET /api/novel/books/{id}/chapters/{n}/score（全話分）
  ```
  `docs/STATUS.md` §7 の K1-K3「実書籍実測値は null」を今回の値で差し替える。K2/K3（中点・クライマックス位置の収束率）は 1 作品なので母数 1 であることを明記。
  完了判定: **K1-K3 に実測値が入り STATUS §7 が更新済み。**
- **C4 コストと伏線 KPI の実測** — 以下を記録:
  ```bash
  curl -s http://localhost:8080/metrics | grep llm_api_tokens_total   # モデル別・prompt/completion 別の累計
  python scripts/report_episode_cost.py --db <sqliteのときのみ> --book-id <id> --json
  curl -s "http://localhost:8080/api/graph/foreshadowing/kpi?book_id=<id>&current_episode=20"
  ```
  1 話あたり LLM 呼出回数（実測 10 回の検証）も `tests/perf/test_v6_llm_call_budget.py` の計測条件を本番ログで確認（呼出回数をログ/メトリクスから集計）。
  完了判定: **cost/話・tokens/話・伏線 KPI（collection_rate / resolution_rate / overdue）が数値で記録済み。**
- **C5 KPI 実測の文書化と判断ゲート** — 以下を 1 つの表にまとめ `docs/STATUS.md` §7（または §12 に新設「実作品 KPI 実測（2026-11-XX）」）へ記録:
  | KPI | 実測 | 出典 |
  |:---|:---|:---|
  | 完走率（20 話中 N 話） | | C2 |
  | K1-K3（spine） | | C3 |
  | 監査スコア分布 | | C3 |
  | cost/話・tokens/話 | | C4 |
  | 1 話あたり LLM 呼出回数 | | C4 |
  | 伏線 collection_rate / overdue | | C4 |

  この時点で `docs/ROADMAP_NEXT.md` §6 の**判断ゲート（Week 2 相当）**を評価し、以降の TRACK-D と P1 の優先度をユーザーに確認する。
  完了判定: **KPI 表が STATUS に記録され、ユーザーが TRACK-D へ GO を出している。→ G3 通過。**
- **C6（任意・延期可）40 話生成による構造ゲート warn の解禁材料取得** — STATUS §9.2 R1-②（40 話生成 + テンション違反率 ≤ 10% の実測）の材料を得る。コストが 2 倍になるため、ユーザーの承認がある場合のみ実施。実施しない場合は R1-② を P2 以降に延期し記録。
  完了判定: **実施 or 延期の決定が記録済み。**

### TRACK-D: フラグ ON/OFF 判定（D1-D4）

> **担当**: エージェント側（キーは C1 で設定済み）。
> **R6**: 追加生成の上限は「20 話 × 最大 3 作品」。全部で約 80 話以内。
> 判定基準・指標定義は出典計画に従い、本書では重複定義しない。

- **D1 H8 AB の実 LLM 再実施** — `PLAN_H8F_ROLLOUT_12STEPS.md` O7/O8 を実 LLM で実行する:
  - データセット: C2 の実作品（20 話）をベースに `var/ab_datasets/h8-real/` へ整備（コミット対象外）
  - 条件 A（flag=0）/ B（flag=1）で改稿経路を実行（全文再生成を避けるため、**監査不合格話のみ**を対象にすると本数を節約できる。本数は実施前に記録）
  - 指標: H8F O7 の採用率 / 再監査合格率 / `audit.regeneration.full` 件数 / `llm_api_tokens_total` 増分
  - 判定: H8F O9 の表をそのまま適用
  完了判定: **D1/D2 の判定表が O9 の基準で埋まり、`docs/STATUS.md` §11 に記録済み。**
- **D2 RAG AB の実施** — `PLAN_R5_RAG_WIRING_24STEPS.md` F1-F3 を最小構成で実行:
  - 最小構成: 条件 off / 条件 full（B+C+D+E 全 ON）× 同一パラメータで 1 作品ずつ（20 話 × 2 本）。4 条件の全マトリクス（F1 完全版）は追加 2 本を要するため、**最小構成で判定基準を満たす/満たさないを先に確認**し、境界付近のときのみ追加（ESR）
  - 指標: F3 の基準（`character_consistency` +2.0 点以上 / コスト増 ≤ +5% / レイテンシ p95 ≤ +1s）
  - **制限の明記**: 人手相関（F2）は今回スコープ外。スコアは監査の dimension スコアを代用し、「人手相関未検証」を判定表に明記する
  完了判定: **RAG フラグ群の既定値が決定（ON はフラグ単位で判断・OFF 維持でも理由を記録）。**
- **D3 伏線 LLM 投票の shadow 計測** — `ENABLE_FORESHADOW_LLM_VOTE=shadow` で D1/D2 の生成を走らせ（追加本数ゼロで回せる）、STATUS §9.2 R1-④ のゲートを評価:
  ```bash
  python -m scripts.analyze_foreshadow_vote_agreement
  ```
  - 一致率 ≥ 0.70 かつ metadata 過大申告が有意なら `mainline` 化を判定に進める。**過大申告が無ければ mainline 化は見送り**（SSOT 記載どおり）
  完了判定: **一致率と過大申告の実測が記録され、`shadow` 継続 / `mainline` 化の判定が出ている。**
- **D4 判定の適用と文書化** — H8F O10-O12 の手順に従う:
  1. ON 化が決まったフラグのみ既定値を変更（`src/agents/audit_agent/config.py` 等の該当 1 行）+ `.env.example` に説明追記 + 対応 contract テストの既定値 assert 更新
  2. 段階解禁: まず計測環境 1 作品 → 観測（`audit_revision_total{outcome="rejected"}` 急増・P95 悪化で即ロールバック）
  3. `docs/STATUS.md` §10/§11 に判定表・根拠・再判定条件を記録。OFF 維持の場合も「再挑戦条件」を 1 行で記録
  4. `docs/ROADMAP_NEXT.md` §5 P0 に実施結果サマリを追記し、G4 を通過させる
  完了判定: **判定表が STATUS に記録され、コード変更（あれば）が 1 コミットにまとまっている。→ G4 通過・P0 完了。**

---

## 4. 判断ゲート

| ゲート | 条件 | 通過後 |
|:---|:---|:---|
| **G1** | CI が発火し全 job 緑（A5） | TRACK-B 解禁 |
| **G2** | 本番で E2E 完走（B4/B6） | TRACK-C 解禁 |
| **G3** | KPI 実測表が記録済み（C5）+ ユーザー GO | TRACK-D 解禁（P1 着手可否も同時に判断） |
| **G4** | 判定表が全項目埋まり P0 完了（D4） | `docs/ROADMAP_NEXT.md` の P1（挿絵 Increment 2 → Play Phase 1）へ |

> いずれのゲートも不通のまま突破しない。3 日以上停滞するゲートは ESR で記録し、ユーザー判断に委ねる。

---

## 5. 検証・リグレッション計画

| ID | 対象 | 内容 | 適用ステップ |
|:---|:---|:---|:---|
| V1 | `make verify` | TRACK 開始前・D4 コミット前に緑であること | 全 TRACK |
| V2 | マイグレーション | `make test-migration`（upgrade → downgrade → upgrade 往復） | B3 前後 |
| V3 | メトリクス無音性 | flag OFF で `audit_*` / `foreshadowing_*` カウンタが増えない | B5 |
| V4 | バイト同一契約 | D4 で ON 化した場合も `test_rag_prompt_injection` / `test_h8_lessons_prompt_injection` / `test_spine_prompt_injection_*.py` が緑 | D4 |
| V5 | ロールバック | flag 1 本で旧挙動へ戻ることを計測環境で実演 | D4 |
| V6 | 認証ガード | 本番で未認証 API が 401 | B4 |

---

## 6. リスクと緩和

| リスク | 影響 | 緩和 |
|:---|:---|:---|
| GitHub 設定の原因が特定できない（A2） | 高 | 原因候補を 5 系統で列挙済み（§3 TRACK-A）。全て不具合なら GitHub Support /別ホストの runner で切り分け。CI 無しで B/C/D を進めるかはユーザー判断（Deviation 記録必須） |
| 実 LLM のコスト超過 | 中 | R6 の本数上限（20 話 × 最大 4 作品）を厳守。tier1 系モデル優先。`llm_api_tokens_total` を C4 で早期に可視化 |
| 実生成が話単位で連続失敗し完走しない | 中 | 失敗自体が KPI（完走率）として価値がある。`retry_failed` を 1 回のみ許可し、それでも不達なら「完走率 N%」として記録（R1 原則） |
| `measure_spine_alignment.py` が PostgreSQL で動かない | 低 | ESR で記録し、SQLite 計測用の dump or スクリプト修正（別ステップ）に分離 |
| 挿絵 WIP との競合（同一ツリー） | 中 | R5: 本計画は `plans/`・`docs/`・`.env`（コミット外）・D4 の 1 行のみ触る。`git add` は常にファイル指定 |
| 生成結果の NSFW/コンテンツ問題 | 低 | `ENABLE_NSFW=false` 既定を維持。計測環境は公開しない（CORS_ORIGINS は実オリジンのみ・8080 は必要時のみ開放） |
| 判定材料が 1 作品分で統計的に弱い | 中 | 母数の弱さを判定表に明記。ON 化は「段階解禁（1 作品 → 3 日観測 → 全書籍）」でリスクを分散 |

---

## 7. 受け入れ条件（Definition of Done）

1. TRACK A-D の全ステップが完了し、G1-G4 を通過している（延期ステップ C6 は決定記録があれば可）
2. `docs/STATUS.md` に「実作品 KPI 実測」の表と「フラグ判定表」が記録されている（ON 化・OFF 維持のいずれでも）
3. K1-K3 の実書籍実測値が STATUS §7 の null から差し替わっている
4. D4 で ON 化したフラグは contract テストの既定値 assert が更新され、CI で常時検証されている
5. CI の発火状況について、CHANGELOG / ROADMAP / 本計画間の記述矛盾が解消されている（CHANGELOG への訂正注記含む）
6. `docs/ROADMAP_NEXT.md` §5 P0 に実施結果サマリが追記され、P1（挿絵 Increment 2）への移行判断が記録されている

---

## 8. 工数と実費の目安

| TRACK | 工数（人日） | 実費 | 備考 |
|:---|:---:|:---|:---|
| A: CI 復活 | 0.5 + 待ち | 0 円 | A2 はユーザー側。GitHub Billing が原因なら追加費用が発生する可能性 |
| B: デプロイ | 2.0 | ホスト費用のみ | 既存 checklist を流用 |
| C: 生成・KPI | 3.0 | 20 話 × 1 作品分 | モデル次第（tier1 系で概ね数百円相当の見込み。**実費は未確認 — C4 の実測で確定させる**） |
| D: フラグ判定 | 5.0 | 20 話 × 最大 3 作品分 | 最小構成で 2 作品に抑えられる可能性（D2 の ESR） |
| **合計** | **約 10.5** | — | ほとんどが運用・計測。ソースコード変更は D4 の 1 行が本計画の上限 |

---

## 9. ESR（Escalation）

本書に記載のない判断・想定外の障害は、**当該ステップをスキップして記録**し TRACK 終端の retro に回す。推測で編集しない。

| 状況 | 処置 |
|:---|:---|
| `gh` CLI 未導入 | ブラウザ UI で代替。`gh api` の手順は**無認証で読める public REST エンドポイント（runs / workflows 等）に限り**代替可。認証必須エンドポイント（`/actions/permissions` 等）は代替不可（2026-11-26 実測: 401）→ ユーザー側確認が必要（D-3 参照） |
| docker が実行ホストで使えない | デプロイ先をクラウド VM 等へ変更し Deviation 記録 |
| API キーが入手できない | TRACK-C を mock のまま実施して KPI 表の該当行を「未測定」とし、G3 は不通としてユーザー判断へ |
| TRACK-A が 3 日以上停滞 | CI 無しで B 以降を進めるかをユーザーに確認（品質ゲートは `make verify` ローカル実行で代替・記録必須） |

---

## 10. 実施記録

### 10.1 TRACK-A（2026-11-26 実施）

| TRACK | ステップ | 状態 | 実施結果 |
|:---|:---|:---:|:---|
| A | A1 push と観測 | ✅ | `git push origin main` → **Everything up-to-date**（origin/main = `fa88fe1a`、`ls-remote` で一致確認）。push 自体は届いている |
| A | A2 設定切り分け（ユーザー） | ⏸ ESR | `gh` 未導入のため GitHub REST API（無認証）で代替実施。**判明した実測**: ① 6 workflows すべて `state: active`（ci.yml 含む、updated 2026-11-23）② main ブランチの runs = **0 件** ③ リポジトリ全体 32 runs・最終発火 2026-11-03 16:38（`lp.yml` × feature branch・failure）④ `/actions/permissions` は 401（認証必須）。**結論: workflow ファイル側は正常、不発はリポジトリ/アカウント設定レベルで確定。** Settings（Actions 有効化・Billing）の確認は**ユーザー側タスクとして残置** |
| A | A3 workflow 登録確認 | ✅ | `ci.yml` は workflows API に registered・active。YAML パース失敗は解消済みと確認（`test_workflow_syntax.py` の対象領域） |
| A | A4 実発火確認 | ⏸ ESR | A2（ユーザー側設定）が解けない限り発火しない。**本計画ではここで停止し、P1 へ進行**（根拠は §10.4 D-1: ユーザーの 2026-11-26 指示。ESR §9 の「3 日以上停滞」条項は未達のため適用外） |
| A | A5 CI 緑確定 | ⏸ ESR | 未達。ただし記述矛盾の解消は実施済み: ① `docs/ROADMAP_NEXT.md` §3 課題A と本書 §1.1 に 2026-11-26 実測を反映 ② `CHANGELOG.md` Unreleased に Q7「CI 復活」記載の訂正注記を追加（A5 の割当タスクとして実施） |

### 10.2 TRACK-B/C/D（ESR 記録 — 2026-11-26 時点の実行環境）

| TRACK | ステップ | 状態 | 実施結果 |
|:---|:---|:---:|:---|
| B | B1 ホスト前提 | ⏸ ESR | 実行ホストに `docker` / `docker compose` が**未導入**（`which docker` 実測）。デプロイ先をクラウド VM 等へ変更するか、ホストへ docker 導入するかは**ユーザー判断**として残置 |
| B | B2-B6 | ⏸ | B1 依存。`.env` 生成手順（B2）は実行可能だが、鍵の発行はユーザー側。未実施 |
| C | C1 プロバイダ設定 | ⏸ ESR | **LLM API キーが環境に存在しない**（`LLM_PROVIDER=mock` のまま）。キー発行はユーザー側。実費が発生するため、キー提示待ち |
| C | C2-C6 | ⏸ | C1 依存。**未実施**。KPI 実測表は `docs/STATUS.md` に未記録（STATUS §7 の K1-K3 は null のまま・§5.4 の「未計測」は 2026-09-29 の記録であり今回のものではない）。ESR §9 の「mock で TRACK-C を実施し該当行を未測定とする」処置は、mock 生成を実際に走らせる運用判断を要するため未適用（再開条件: B1/C1 解消後に可否を再判断） |
| D | D1-D4 | ⏸ | C 依存。フラグ判定は**既定 OFF 維持のまま**（R1 原則: 判定不通なら OFF 維持。実 LLM 計測が完了するまで再判定しない） |

### 10.3 ゲート状態

| ゲート | 状態 |
|:---|:---|
| G1（CI 緑） | ❌ 不通（A2 がユーザー側ブロッカー） |
| G2（E2E 完走） | ❌ 不通（B1 docker 未導入） |
| G3（KPI 実測） | ❌ 不通（C1 API キーなし） |
| G4（判定完了） | ❌ 不通（C 依存） |

### 10.4 進行方針と Deviation 記録（P12・2026-11-26）

- **D-1**: G1-G4 が不通のまま **P1 へ進行する**。§4 ゲート設計（G4 通過後に P1 解禁）からの逸脱であり、根拠は**ユーザーの 2026-11-26 指示「P0→P1 の順序で最後まで実装せよ」**。
  - 進行対象のうち「挿絵 Increment 2」はゲート前提を持たないためそのまま実施する
  - 「Play Phase 1」は `docs/ROADMAP_NEXT.md` §5 P1-3 の前提（P0 の KPI 基盤）を**満たさない**ため、**実装を先行し KPI 計測（cost/play・完走率等）は P0 再開後に取得する**（実装完了・計測待ち）。完了判定は P0 の G3 通過後に後付けする（`plans/PLAN_P1_PLAY_ILLUSTRATION_16STEPS.md` §4 の G-KPI と同型）
- **D-2**: A2 未解消のまま TRACK-B 以降へ進む場合（B1/C1 のみ解消のケース）は、品質ゲートを `make verify` のローカル実行で代替し、G1 は「未達」のまま記録する
- **D-3**: ESR §9 の「`gh api` は REST 呼び出しで代替可」は**無認証で読める public エンドポイント（runs / workflows 等）に限る**。認証必須エンドポイント（`/actions/permissions` 等）は 401 実測により代替不可
- **D-4**: 挿絵 Increment 1 は並行作業セッションにより `8ddfe522`+`fa88fe1a` としてコミット・push 済み（`docs/ROADMAP_NEXT.md` §5 P1 の「コミット」ステップは完了）

**A2（ユーザー側）の再開条件**: GitHub Settings で Actions の有効化 / Billing を確認・変更した後、main に 1 コミット push して **check runs ≥ 1 を観測できたら A4/A5 を再実行**し、G1 を再評価する。TRACK-A はこの再開条件が満たされるまで残置とする。

---

## 11. 関連ドキュメント

| ドキュメント | 関係 |
|:---|:---|
| [`docs/ROADMAP_NEXT.md`](../docs/ROADMAP_NEXT.md) | 本計画の上位文書（§5 P0） |
| [`docs/STATUS.md`](../docs/STATUS.md) | 実装状況 SSOT。KPI・判定表の記録先（§7 / §10 / §11） |
| [`docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md`](../docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md) | デプロイ手順・ロールバックの SSOT |
| `plans/PLAN_H8F_ROLLOUT_12STEPS.md` | D1 の AB 手順・判定基準（O7-O9）の出典 |
| `plans/PLAN_R5_RAG_WIRING_24STEPS.md` | D2 の AB 設計（F1-F3）の出典 |
| `plans/PLAN_J1_REMAINING_36STEPS.md` | 分割原則（§0.1）の継承元 |
| `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` | CI ブロック状況の記録（§7）。G1 通過後に更新 |

---

## 改訂履歴

| 日付 | 版 | 内容 |
|:--|:--|:---|
| 2026-11-25 | 0.1 | 初版作成（`docs/ROADMAP_NEXT.md` §5 P0 の実行計画書として起票・承認待ち） |
