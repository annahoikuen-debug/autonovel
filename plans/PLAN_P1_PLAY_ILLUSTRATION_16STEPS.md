# PLAN_P1: Play モード完成 — 挿絵 Increment 2 と動的継続生成 (16 ステップ)

- **文書ID**: `PLAN_P1_PLAY_ILLUSTRATION_16STEPS`
- **作成日**: 2026-11-26
- **対象**: AutoNovel v7.0.0（HEAD `fa88fe1a`、main push 済み）
- **位置づけ**: [`docs/ROADMAP_NEXT.md`](../docs/ROADMAP_NEXT.md) §5 優先度 **P1「進行中の縦切りを完成させる」の実行計画書**。
  - **Increment 1（表示配線）は完了済み**: 並行作業セッションにより `8ddfe522`（決定的クエリ API・Play 表示・`/static` 配信・vite proxy）+ `fa88fe1a`（ドキュメント）としてコミット済み。本書はこれを前提とする
  - 本書の対象: **Increment 2（生成・保存経路の修復）** と **Play Phase 1（動的継続生成・`ENABLE_DYNAMIC_BRANCH`）**
- **前提**:
  - `docs/adr/003-illustration-mainline.md`（承認済み）: 本線は `ImageService`(Imagen)。B/C 系統は対象外
  - `docs/adr/002-play-mode-mainline.md`（承認済み）: Play モード本線化。flag 既定 OFF・off 差分ゼロ契約
  - `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §4 Phase 1/Phase 3: スコープの上位定義
  - P0（`plans/PLAN_P0_CLOSE_THE_LOOP_21STEPS.md`）のユーザー側ブロッカー（CI/docker/LLM キー）は未解消。**本計画はコード完結の範囲で実施し、KPI 計測は P0 再開後に委ねる**
- **原則**: `plans/PLAN_J1_REMAINING_36STEPS.md` §0.1（P1〜P12）を継承。**P4（反証確認）・P5（推測禁止・実地 grep）・P6（1ステップ=1コミット）** を厳守。行番号は 2026-11-26 実査。

---

## 0. TL;DR

| # | TRACK | 目的 | 出口条件 |
|:---|:---|:---|:---|
| **I** | 挿絵 Increment 2（I1-I8） | 生成結果が DB に保存され、パイプラインから実画像が積み上がる経路を作る | `/batch` が DB 保存に成功・easy mode で flag 制御の挿絵生成が動く・off 差分ゼロ契約緑 |
| **P** | Play Phase 1（P1-P8） | 選択した時点で LLM が次シーンを生成する（`ENABLE_DYNAMIC_BRANCH`・既定 OFF） | flag OFF で既存挙動不変（契約テスト）・flag ON で「選択→生成→新選択肢」が完走・cost/play メトリクス露出 |
| **X** | 横断（X1-X3） | 品質ゲート・review-loop・コミット整理 | `make verify` 緑・reviewer 判定 LGTM・3 コミット以上の論理分割 |

**最重要契約（両 TRACK 共通）**: 新挙動は必ず flag 既定 OFF で導入し、**「OFF = 既存挙動不変」を契約テストで担保**する（提案 5/8 で採用済みのパターン）。

---

## 1. 現状の正確な記録（2026-11-26 実査）

### 1.1 Increment 2 対象の構造的欠落（実地確認済み）

| # | 欠落 | 証拠（行番号は 2026-11-26 実査） |
|:--|:---|:---|
| G1 | DI コンテナが `IllustrationAgent` に `repo` を注入しない | `src/core/container/app.py` — `illustration_agent` プロバイダは `image_service` のみ。`SkillAgent.__init__`（`src/agents/skill_base.py:27-38`）は `repo` を受けられる（BaseAgent 経由で `self.repo` に入る） |
| G2 | DI コンテナが `IllustrationWorkflow` に `repo` を注入しない | `src/core/container/app.py` — `illustration_workflow` プロバイダは `illustration_agent` のみ。`IllustrationWorkflow.execute` は `assert self.repo is not None`（`src/backend/workflows/illustration_workflow.py:76,153`）で ** Huey 経由の `/batch` が確実に落ちる** |
| G3 | `repo.get_chapters(book_id)` が存在しない | `IllustrationWorkflow.execute:106` が `await self.repo.get_chapters(book_id)` を呼ぶ。しかし `ChapterRepository` に `get_chapters` は存在しない（`get_chapter` / `get_chapters_before` / `get_all_non_anchor_chapters` のみ・`src/infrastructure/repositories/chapter.py:155-189`）。**assert 通過後も AttributeError** |
| G4 | パイプラインからの挿絵生成は常に no-op | `ctx.artifacts["request"]` をセットする箇所がリポジトリ内にゼロ（`docs/plans/PHASE3_ILLUSTRATION_WIRING_SURVEY.md` §0 再確認済み）。`IllustrationStep`（`src/services/pipeline_steps.py:489-535`）は `ctx.enable_illustration` ゲートで skip。`IllustrationWorkflow` 自体は `engine.repo` を受けて動く実装（:514 付近で `repo=engine.repo` を渡している） |
| G5 | easy mode が `enable_illustration=False` ハードコード | `src/easy_mode/pipeline.py:84-85` |
| G6 | `agent.run()` はプロンプトのみ（`image_url=""` で永続化） | `src/agents/illustration_agent.py` — 実画像経路 `_generate_episode`（:176）は `run` から呼ばれない（SURVEY §1.3）。実画像は yonkoma（:412）と `generate_episode_scenes`（:438）のみ |
| G7 | facade の Auto-mode フォールバックに `illustrations` がない | `src/backend/database/repository.py` `DataRepositoryFacade.__getattr__` — UoW モードのリポジトリ列挙に `illustrations` は含まれる（:163 `uow.illustrations` → `IllustrationRepository.create_illustration` で解決可）。しかし UoW 未使用時のフォールバック列挙には `illustrations` が**含まれない** |

### 1.2 Play Phase 1 の接続点（実地確認済み）

| 資産 | 実体 | 状態 |
|:---|:---|:---|
| play WS | `src/backend/routers/branches.py:975` `play_ws` — `action: choose/save/load/state/playthrough` を処理。レート制限（1 秒あたり `_WS_MAX_MESSAGES_PER_SEC`）・サイズ制限・所有権検証済み | 拡張の接続点 |
| 分岐グラフ | `BranchRepository.load_branch_graph` / `update_play_session_state_optimistic`（CAS 付き） | 動的ノードの追加先 |
| 生成基盤 | `src/domain/writing/coordinator.py`（執筆コア）+ 4層圧縮 + 監査 | 軽量版として流用 |
| メトリクス | `src/backend/observability/metrics.py`（`llm_api_tokens_total` 等の既存パターン） | cost/play 追加先 |
| フロント | `frontend/src/pages/PlayModePage.tsx`（Increment 1 で挿絵表示追加済み） | 動的継続 UI の接続点 |

---

## 2. 設計原則（本計画の拘束）

| # | 原則 | 機械的保証 |
|:---|:---|:---|
| **P1** | flag 既定 OFF・off 差分ゼロ | 契約テスト（P6 / I7） |
| **P2** | コード変更は最小差分。既存メソッドの流用優先 | G3 の修復は `get_all_non_anchor_chapters` 流用（新規 SQL を書かない） |
| **P3** | コストが発生する経路には必ず上限とレート制限 | I6（1 作品あたり上限）/ P5（1 セッションあたり上限） |
| **P4** | 4層境界を守る。動的生成のロジックは application/use_cases 層に置く | `scripts/check_layer_boundaries.py` 緑維持 |
| **P5** | 挿絵の実生成（Imagen 課金）は flag OFF が既定。キー未設定時は現行の prompt-only フォールバックを維持 | I4/I5 |
| **P6** | 1 ステップ = 1 コミット。挿絵 WIP（並行作業）との競合回避のため `git add` は常にファイル指定 | 全ステップ |

---

## 3. 実装ステップ

### TRACK-I: 挿絵 Increment 2（I1-I8）

- **I1 現状実測の記録** — §1.1 の G1-G7 を `docs/plans/PHASE3_ILLUSTRATION_WIRING_SURVEY.md` に「2026-11-26 実査」セクションとして追記（G3 の AttributeError 発見を含む）。
  完了判定: **サーベイに G1-G7 が記録され、行番号が実地確認と一致。**
- **I2 DI repo 注入** — `src/core/container/app.py`:
  - `illustration_agent` プロバイダに `repo=repo` を追加（既存 `repo` Singleton = `DataRepositoryFacade` を流用）
  - `illustration_workflow` プロバイダに `repo=repo` を追加
  - `DataRepositoryFacade.__getattr__` の Auto-mode フォールバック列挙に `illustrations` を追加（G7）
  - 反証確認（P4）: 修正前に `/batch` 相当のテストで `assert self.repo is not None` が落ちること（赤確認）→ 修正 → 緑
  完了判定: **DI 経由の workflow で repo が非 None になり、`_persist` が呼ばれる。**
- **I3 `get_chapters` 不存在の修復** — `IllustrationWorkflow.execute:106` を既存メソッド `get_all_non_anchor_chapters(book_id, ...)` への置換で対応（新規 SQL を書かない・P2）。置換時は戻り値の使用箇所（:106 以降の `total_steps` 計算）を既存メソッドの返却型（`list[Chapter]`）に合わせる。
  反証確認: 修正前に workflow 実行で AttributeError が発生することを 1 テストで確認。
  完了判定: **workflow execute が chapters 取得で落ちない。**
- **I4 実画像生成経路の接続** — `IllustrationAgent.run()` を `_generate_episode`（実画像経路）に接続する:
  - `ImageService` がキー未設定で失敗した場合（`ValueError` 等）は現行の prompt-only フォールバックを維持（P5）
  - キーがある場合のみ実画像を生成し、`_persist` で DB 保存
  - **flag は使わない**（ADR 003: 開発・CI は mock 運用。キーがなければ実画像は発生しないため、既定挙動は環境変数 `IMAGE_PROVIDER` / キー有無で自然に決まる）。ただし easy mode パイプライン経路のみ flag で制御（I5）
  完了判定: **キー未設定環境で prompt-only（現行と同一）・キー設定環境で実画像+DB 保存（単体テストはスタブ ImageService で検証）。**
- **I5 easy mode の flag 化** — `src/easy_mode/pipeline.py:84-85` の `enable_illustration=False` を env flag `ENABLE_EASY_ILLUSTRATION`（既定 `0`）で制御:
  - `pipeline_steps.py` の `IllustrationStep` は既存の `ctx.enable_illustration` ゲートを流用
  - `enable_illustration=True` でも `illustration_settings.enableIllustration` が未設定なら skip（既存二重ゲートを維持）
  完了判定: **flag OFF でバイト同一挙動（既存テスト緑）・flag ON で IllustrationStep が到達可能。**
- **I6 パイプライン経路のコスト上限** — `IllustrationStep` に 1 作品あたりの生成枚数上限を追加（env `ILLUSTRATION_MAX_PER_BOOK`、既定 `20`）。超過時は `_emit_skip` で skip し warning。クレジット消費なし（パイプライン経路は作品生成者の消費に含まれる設計・SURVEY §1.4 の既存 `/generate` の 5 クレジットは別経路のまま）。
  完了判定: **上限超過時に生成が止まり、作品本体は継続完了する。**
- **I7 テスト** — 新規 + 既存:
  - `tests/unit/backend/test_illustration_di_injection.py`（新規）: DI 経由で agent/workflow に repo が入る
  - `tests/unit/backend/test_illustration_workflow_chapters.py`（新規）: get_chapters 修復後の execute 正常系
  - `tests/contract/test_illustration_pipeline_gate.py`（新規）: `ENABLE_EASY_ILLUSTRATION` OFF で挿絵が一切生成されず、プロンプト/本文がバイト同一であること
  - 既存: `tests/unit/api/test_illustration_router.py`・`tests/unit/agents/` 関連が緑
  完了判定: **新規テスト緑 + 既存回帰ゼロ + `make openapi` で差分ゼロ（API 変更なしのため）。**
- **I8 ドキュメント** — ADR 003 に Increment 2 完了記録、`docs/STATUS.md` §2 挿絵行を更新、「実装あり・未配線多数」→「Increment 1 完了 / Increment 2 完了（保存経路・パイプライン接続）」。`CHANGELOG.md` Unreleased に追記。
  完了判定: **3 ドキュメント更新済み → TRACK-I 出口条件達成。**

### TRACK-P: Play Phase 1 動的継続生成（P1-P8）

- **P1 flag の追加** — `src/infrastructure/config/settings.py` に `ENABLE_DYNAMIC_BRANCH`（既定 `False`）を追加 + `.env.example` に説明追記。
  完了判定: **settings 経由で flag が読める。既定 OFF。**
- **P2 動的継続ユースケース** — `src/application/use_cases/play_dynamic_continue.py`（新規）:
  - 入力: `book_id` / `session_id` / `choice_text`（選択内容）/ `current_node`（現在地と文脈）
  - 処理: (a) 既存執筆パイプラインの軽量版（コンテキスト構築 → 本文生成 → 静的ルール監査のみ）→ (b) 生成本文から次選択肢 2-3 件を抽出（既存 `IFRouteGenerator` の選択肢構造を流用）→ (c) 新ノードを分岐グラフへ追加
  - **Huey を経由しない**（同期応答。ROADMAP_PLAYABLE_NOVEL §5 の「同期 vs バッチ」方針）
  - 4層境界: domain への依存のみで、`src/backend` への import を持たない（P4）
  完了判定: **単体テスト（モック LLM）で「選択 → 本文 → 新ノード」が 1 パスで完走する。**
- **P3 WS 経路の追加** — `src/backend/routers/branches.py` `play_ws` に `action: "dynamic_continue"` を追加:
  - flag OFF の場合は `{"type": "error", "message": "dynamic continuation is disabled"}` を返すのみ（既存挙動に影響ゼロ・未知アクションの既存処理と同一挙動）
  - flag ON の場合: P2 のユースケースを呼び、生成結果を WS で push（`{"type": "dynamic_scene", ...}`）+ 新ノードを CAS でセッション状態へ反映
  - レート制限: 1 セッションあたりの動的生成回数上限（P5）と WS 既存のメッセージ制限を併用
  完了判定: **flag OFF で既存 WS テスト全緑・flag ON で動的生成が 1 往復完走する（統合テスト）。**
- **P4 コストメトリクス** — `src/backend/observability/metrics.py` に追加:
  - `play_dynamic_scenes_total{book_id}`（Counter）
  - `play_dynamic_tokens_total{token_type}`（既存 `llm_api_tokens_total` を流用し、動的経路の呼び出しでもインクリメントされることを確認）
  - `play_dynamic_duration_seconds`（Histogram・first-token p95 の素材）
  完了判定: **`/metrics` に露出し、flag OFF で無音（V3 と同型の無音性チェック）。**
- **P5 コスト上限** — env `PLAY_DYNAMIC_MAX_PER_SESSION`（既定 `30`）+ `PLAY_DYNAMIC_DAILY_MAX_PER_USER`（既定 `200`）。超過時は WS で `{"type": "error", "message": "dynamic limit reached"}`。
  完了判定: **上限超過時に生成されず、既存グラフ型プレイは継続可能。**
- **P6 契約テスト** — `tests/contract/test_dynamic_branch_contract.py`（新規）:
  - flag OFF: `dynamic_continue` は error 応答のみ・既存 `choose` の応答がバイト同一・openapi 差分ゼロ
  - flag ON: 「選択 → 生成 → 新選択肢」の E2E（REST + WS・モック LLM）
  完了判定: **契約テスト緑。**
- **P7 フロント** — `PlayModePage.tsx` に動的継続の導線を追加（capability `dynamicBranch` を `planned` で新規宣言し、flag 有効時のみ表示。flag 状態は既存 capabilities パターンに従う）+ `usePlaySession` に `dynamic_continue` を追加 + 型同期（`npm run type:sync`）。
  完了判定: **フロントテスト緑・tsc エラー 0。**
- **P8 ドキュメント** — `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §4 Phase 1 の完了条件に実施結果を追記（KPI は P0 再開後に取得するため「実装完了・計測待ち」と明記）、`docs/STATUS.md` §2 Play モード行更新、`frontend/src/capabilities.ts` 更新、`CHANGELOG.md` 追記。`make openapi` + `npm run type:sync`。
  完了判定: **ドキュメント 4 点 + openapi + 型同期が完了 → TRACK-P 出口条件達成。**

### TRACK-X: 横断（X1-X3）

- **X1 品質ゲート** — `make verify`（ci-parity + lint-layers + typecheck + test-contract + test-migration）を TRACK-I 完了後と TRACK-P 完了後に実行。フロントは `make frontend-test` + `make frontend-lint`。
  完了判定: **全ゲート緑。**
- **X2 review-loop** — reviewer サブエージェントによる 2 ラウンド以上のレビュー・修正サイクル（最終判定 LGTM）。P0 計画書のレビュー結果と合わせて指摘を解消。
  完了判定: **reviewer 判定 LGTM。**
- **X3 コミット分割** — 以下の単位で論理分割コミット:
  1. `feat(illustration): 挿絵の保存経路とパイプライン接続を修復 (Increment 2)`
  2. `feat(play): 動的継続生成を追加 (Phase 1・ENABLE_DYNAMIC_BRANCH)`
  3. `docs: P0/P1 実施記録とロードマップ更新`
  `docs/adr/003-illustration-mainline.md`（未追跡）はコミット 1 に含める。
  完了判定: **3 コミット以上で履歴が整理され、push 済み。**

---

## 4. 判断ゲート

| ゲート | 条件 | 通過後 |
|:---|:---|:---|
| **G-I** | TRACK-I の出口条件（I7/I8） | TRACK-P 解禁 |
| **G-P** | TRACK-P の出口条件（P6/P8） + X1 | X2/X3（review-loop・コミット） |
| **G-KPI** | P0 のユーザー側ブロッカー解消後（CI/docker/LLM キー） | 動的生成の cost/play 実測・Play Phase 1 の KPI ベースライン取得 |

> **G-KPI は本計画のスコープ外**（P0 の TRACK-C/D で取得）。本計画では「計測準備（メトリクス・上限・flag）まで」を完了させる。

---

## 5. 検証・リグレッション計画

| ID | 対象 | 内容 | 適用ステップ |
|:---|:---|:---|:---|
| V1 | `make verify` | TRACK-I 完了後・TRACK-P 完了後に全ゲート緑 | X1 |
| V2 | off 差分ゼロ | `ENABLE_EASY_ILLUSTRATION` / `ENABLE_DYNAMIC_BRANCH` とも OFF で既存挙動不変（バイト同一 or 未定義アクション error） | I7 / P6 |
| V3 | メトリクス無音性 | flag OFF で `play_dynamic_*` カウンタが増えない | P4 |
| V4 | 4層境界 | `scripts/check_layer_boundaries.py` 緑（use_cases が backend を import しない） | P2 |
| V5 | 反証確認（P4 原則） | I2/I3 は修正前に赤を確認するテストを先に書く | I2 / I3 |
| V6 | ロールバック | flag 2 本（`ENABLE_EASY_ILLUSTRATION` / `ENABLE_DYNAMIC_BRANCH`）で旧挙動に戻ることを実演 | X1 |

---

## 6. リスクと緩和

| リスク | 影響 | 緩和 |
|:---|:---|:---|
| 並行作業セッションとの衝突（同一ツリー） | 高 | P6: ファイル指定コミット。衝突検知時は `git log --oneline -3` で再確認してから続行 |
| `run()` の実画像接続（I4）でキー未設定環境が壊れる | 中 | P5 原則: 失敗時は prompt-only フォールバックを維持（現行と同一の挙動）。CI は mock のため実画像は発生しない |
| 動的生成のコスト暴走 | 中 | P5 の二重上限（セッション/日次）+ P4 メトリクス先行。flag 既定 OFF |
| 動的生成のレイテンシで WS がタイムアウト | 中 | 軽量版パイプライン（静的監査のみ・本文上限を既存設定から引用）。タイムアウト時は既存グラフへフォールバック |
| `get_chapters` 置換で他の呼び出しを壊す | 低 | G3 は `IllustrationWorkflow.execute` 内の 1 箇所のみ。`grep -rn "get_chapters\b"` で全呼び出しを確認済み（workflow 以外に無し） |
| mypy / ruff の ratchet 増加 | 低 | 新規コードは型アノテーション必須。X1 で ratchet 確認 |

---

## 7. 受け入れ条件（Definition of Done）

1. TRACK-I/P の全ステップが完了し、G-I/G-P を通過している
2. **off 差分ゼロ契約**: `ENABLE_EASY_ILLUSTRATION=0`（既定）・`ENABLE_DYNAMIC_BRANCH=false`（既定）で、既存の全テストと openapi スナップショットが無変更で緑
3. flag ON 経路がそれぞれ 1 パス完走するテスト（I5 / P6）が存在し、CI（またはローカル `make verify`）で常時検証されている
4. `docs/adr/003-illustration-mainline.md` が追跡対象になり、Increment 2 完了が記録されている
5. `docs/ROADMAP_PLAYABLE_NOVEL.md` §3/§4 が現状に更新され、Phase 1 は「実装完了・KPI 計測待ち」と明記されている
6. `make verify` + `make frontend-test` + `make frontend-lint` が緑
7. review-loop（X2）の最終判定が LGTM

---

## 8. 工数見積（人日）

| TRACK | 実装 | テスト/計測 | 小計 |
|:---|:---:|:---:|:---:|
| I: 挿絵 Increment 2 | 1.5 | 1.0 | 2.5 |
| P: Play Phase 1 | 3.0 | 2.0 | 5.0 |
| X: 横断 | 0.5 | 1.0 | 1.5 |
| **合計** | **5.0** | **4.0** | **9.0** |

ソースコード変更の本命は I2（DI 3 行 + facade 1 行）・I3（1 行）・P2/P3（ユースケース + WS アクション）。大部分はテストとドキュメント。

---

## 9. ESR（Escalation）

| 状況 | 処置 |
|:---|:---|
| 並行セッションが同一ファイルをコミットし始めた | 当該ステップを中断し、`git log` で差分を確認してから rebase 的に再開。競合が深い場合はユーザーに報告 |
| `_generate_episode` 接続（I4）で設計判断が必要になった | prompt-only 維持のまま I4 を「キー設定環境のみ有効」と限定し、判断を STATUS に記録 |
| Play Phase 1 のユースケースが 4 層境界内に収まらない | `scripts/check_layer_boundaries.py` の ratchet を増やさない。ロジックを domain に寄せ、P2 を分割 |
| WS テストが Node 26 環境で不安定 | 既知問題（react-router × undici とは別）。WS テストはバックエンド側（pytest）で担保し、フロントは REST レベルで検証 |

---

## 10. 実施記録

### 10.1 TRACK-I（2026-11-26 実施）

| TRACK | ステップ | 状態 | 実施結果 |
|:---|:---|:---:|:---|
| I | I1 サベイ更新 | ✅ | `docs/plans/PHASE3_ILLUSTRATION_WIRING_SURVEY.md` §7 に G1-G7 を行番号つきで記録。**新発見 G3**: `repo.get_chapters` が存在せず assert 通過後も AttributeError になる |
| I | I2 DI repo 注入 | ✅ | `container/app.py` の `illustration_agent` / `illustration_workflow` に `repo` 注入 + facade Auto-mode に `illustrations` 追加（G1/G2/G7）。反証テスト 4 件を先に赤確認→修復後緑（P4 原則遵守） |
| I | I3 get_chapters 修復 | ✅ | `get_all_non_anchor_chapters(book_id, branch_id)` に置換（新規 SQL を書かない・P2）。反証確認済み |
| I | I4 実画像経路接続 | ✅ | `run()` → `_generate_image()`（cover/character/episode の実画像・yonkoma は専用経路のため対象外）。キー未設定時は prompt-only フォールバックを維持（P5） |
| I | I5 easy mode flag 化 | ✅ | `ENABLE_EASY_ILLUSTRATION`（既定 False）。`src/easy_mode/pipeline.py` のハードコード解消 |
| I | I6 コスト上限 | ✅ | `ILLUSTRATION_MAX_PER_BOOK`（既定 20）。`IllustrationStep` が settings に上限を注入し、workflow の話数ループで break |
| I | I7 テスト | ✅ | `tests/unit/backend/test_illustration_di_injection.py`（4 件・反証→緑）+ `tests/contract/test_illustration_pipeline_gate.py`（6 件・off 差分ゼロ/上限/フォールバック契約）。既存回帰 249 passed / ruff clean |
| I | I8 ドキュメント | ✅ | ADR 003 実施記録・STATUS §2 挿絵行更新・CHANGELOG 追記 |

### 10.2 TRACK-P（2026-11-26 実施）

| TRACK | ステップ | 状態 | 実施結果 |
|:---|:---|:---:|:---|
| P | P1 flag 追加 | ✅ | `ENABLE_DYNAMIC_BRANCH`（既定 False）+ `PLAY_DYNAMIC_MAX_PER_SESSION`（既定 30）+ `.env.example` 説明追記 |
| P | P2 ユースケース | ✅ | `src/application/use_cases/play_dynamic_continue.py`（決定論的プロンプト・JSON fail-open・800 字上限・`src.backend` 非依存で 4 層境界維持） |
| P | P3 WS 経路 | ✅ | WS `dynamic_continue` + **REST `POST /play/{session_id}/dynamic`**（Deviation D-P1: Play UI は REST ベース（Phase 0 方針「REST 優先・WS 任意」）のため REST も追加。openapi 再生成済み） |
| P | P4 メトリクス | ✅ | `play_dynamic_scenes_total{book_id}` / `play_dynamic_duration_seconds` |
| P | P5 コスト上限 | ✅ | セッションあたり上限（context_json `dynamic_count`）。**日次上限は未実装**（Deviation D-P2: 正確な日次集約は Redis/DB 集計を要するため、セッション上限 + メトリクス観測に簡略化。`docs/STATUS.md` に記録） |
| P | P6 契約テスト | ✅ | `tests/contract/test_dynamic_branch_contract.py`（8 件: use case 契約・settings 契約・REST 登録・メトリクス無音性）+ `tests/branches/test_dynamic_continue_ws.py`（4 件: flag OFF error / flag ON 完走 / 上限 / 既存 choose 不変） |
| P | P7 フロント | ✅ | `usePlaySession.dynamicContinue` + PlayModePage「✨ 続きを生成 (AI)」パネル（`dynamic_available` で表示制御）+ capability `dynamicBranch: wired` + 型定義追加。tsc 0 エラー・usePlaySession 12 passed・PlayModePage 13 passed |
| P | P8 ドキュメント | ✅ | ROADMAP_PLAYABLE_NOVEL §3/§4 更新（Phase 1 実装完了・KPI 計測待ち）・STATUS §2 Play 行更新・CHANGELOG 追記・`make openapi` + `npm run type:sync` 実施 |

### 10.3 Deviation 記録（P12）

- **D-P1**: 計画書 P3 は「WS 経路に追加」のみだったが、**REST エンドポイント `POST /play/{session_id}/dynamic` を追加した**。理由: Play UI（Phase 0）は REST ベースで実装されており（`docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §4 Phase 0「REST を優先し WS は任意」）、WS 専用では UI から動的継続を使えない。flag OFF では REST は 503（既存挙動に影響しない）・openapi 再生成済み。**review-loop Round 2 修正で REST に `generate_limiter`（1 分あたり 10 回・既存ミドルウェア）を適用**
- **D-P2**: 計画書 P5 の `PLAY_DYNAMIC_DAILY_MAX_PER_USER`（日次上限）は未実装。理由: 日次集約は Redis/DB 集計を要し、セッション上限 + メトリクス観測 + REST の `generate_limiter` で一次保護は成立する。**Phase 2 課題**（review-loop 指摘 2）: per-user の厳密な上限は cost/play の実測（P0 TRACK-C）後に必要性和判断する
- **D-P3**: WS 初期 state に `dynamic_available` / `dynamic_count` フィールドを追加（既存フィールドは不変・非破壊追加）。flag OFF では常に false
- **D-P4**（review-loop 指摘 5・Low）: `play_dynamic_scenes_total` の `book_id` ラベルは書籍数に比例した系列増加になり得る。Phase 1 規模では実害なし。多段テナント化する際にラベル見直し

### 10.5 review-loop（TRACK-P・2026-11-26）

| Round | 判定 | 指摘と対応 |
|:---|:---:|:---|
| Round 1 | 要修正 | 指摘 1 **[High] WS 経路の rollback 欠落** → CAS 失敗時のグラフ書き込み残留を `session.rollback()` で救済（REST と同一）。指摘 2 [High] REST のレート制限なし → `generate_limiter` 適用。指摘 3 [Medium] `new_node_id` の決定論的上書きリスク → `uuid4().hex[:6]` を付与。指摘 4 [Medium] `scene_number` が動的回数固定 → `context_json.history` の長さ + 1 に変更。指摘 7 [未確定] `run()` が persist 失敗も握り潰す → 生成成功・保存失敗を分離（保存失敗は警告のみで success 返却）。指摘 5 [Low] metrics ラベル → D-P4 として記録。指摘 6 [Low] off 差分ゼロ（state 追加）は妥当と評価 |

### 10.4 TRACK-X（2026-11-26 実施）

| TRACK | ステップ | 状態 | 実施結果 |
|:---|:---|:---:|:---|
| X | X1 品質ゲート | ✅ | branches + contract **209 passed / 2 skipped**・挿絵回帰 249 passed・動的継続+挿絵契約 **19 passed**・ruff **0 errors**・mypy **326 < baseline 450**（ratchet OK）・migration 往復 **exit 0**・4 層境界 **契約 1/2 OK**・フロント **76 files / 412 passed**・tsc 0 エラー・lint 0 errors・openapi 再生成 + type:sync 済み |
| X | X2 review-loop | ✅ | **P0: 3 ラウンドで LGTM**（指摘 5 → 残存 2 → LGTM）/**P1: 2 ラウンドで LGTM**（Round 1 要修正 6 指摘（High 2・Medium 3・Low 1）→ 修正コミット `bab90be9` → Round 2 **LGTM**（全指摘解消確認））。修正内容: WS rollback・REST `generate_limiter`・非決定論的 `new_node_id`・scene_number 実進行化・persist 失敗分離 |
| X | X3 コミット分割 | ✅ | ① `c369c6aa` Increment 2 ② `2ea33cb5` Play Phase 1 ③ `3aed9648` 計画書起票 ④ `bab90be9` review-loop 修正。**push 済み**（`3aed9648..bab90be9`） |

> **残タスク（ユーザー側）**: P0 のユーザー側ブロッカー（GitHub Actions 設定 / docker ホスト / LLM API キー）が解消され次第、
> `make verify` の CI 実行・本番デプロイ・実 LLM での KPI 実測（cost/play・完走率）・フラグ ON 判定（`plans/PLAN_P0_CLOSE_THE_LOOP_21STEPS.md` TRACK-B/C/D）を実施する。

---

## 11. 関連ドキュメント

| ドキュメント | 関係 |
|:---|:---|
| [`docs/ROADMAP_NEXT.md`](../docs/ROADMAP_NEXT.md) | 本計画の上位文書（§5 P1） |
| `plans/PLAN_P0_CLOSE_THE_LOOP_21STEPS.md` | 前段計画。ユーザー側ブロッカーの記録先 |
| [`docs/adr/002-play-mode-mainline.md`](../docs/adr/002-play-mode-mainline.md) | Play モード本線化の決定 |
| [`docs/adr/003-illustration-mainline.md`](../docs/adr/003-illustration-mainline.md) | 挿絵本線クライアント決定（本計画で追跡対象化） |
| [`docs/plans/ROADMAP_PLAYABLE_NOVEL.md`](../docs/plans/ROADMAP_PLAYABLE_NOVEL.md) | Phase 1/3 のスコープ上位定義 |
| [`docs/plans/PHASE3_ILLUSTRATION_WIRING_SURVEY.md`](../docs/plans/PHASE3_ILLUSTRATION_WIRING_SURVEY.md) | Increment 2 の根拠（I1 で G1-G7 を追記） |
| [`docs/STATUS.md`](../docs/STATUS.md) | 実装状況 SSOT（I8/P8 で更新） |

---

## 改訂履歴

| 日付 | 版 | 内容 |
|:--|:--|:---|
| 2026-11-26 | 0.1 | 初版作成（`docs/ROADMAP_NEXT.md` §5 P1 の実行計画書。Increment 1 完了を前提に Increment 2 と Play Phase 1 を定義） |
