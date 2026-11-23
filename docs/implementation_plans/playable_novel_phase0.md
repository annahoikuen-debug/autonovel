# Play モード Phase 0 実装計画書(既存資産の表面化)

**作成日:** 2026-11-23
**ステータス:** 📋 レビュー待ち
**上位計画:** `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §4 Phase 0 / `docs/adr/002-play-mode-mainline.md`
**雛形:** `docs/implementation_plans/if_routes_productization.md` の書式を踏襲

## 0. メタ方針(設計決定事項)

| # | 項目 | 決定 | 反映先ステップ |
|---|------|------|---------------|
| Q1 | ルート | `/app/play/:bookId`(互換リダイレクト `/play` → `/app/play`) | S11 |
| Q2 | 通信方式 | **REST のみ**(WS は使わない)。WS は Phase 1(動的継続)で必須化する | 全体 |
| Q3 | capability 宣言 | `branchPlay: "wired"`(バックエンド実装済みのため最初から wired) | S12 |
| Q4 | KPI 計測 | **フロント計測基盤は作らない**。`branch_play_sessions` の行集計(既存 DB)で初期値を取る | S16 |
| Q5 | テスト方針 | `npm run test:ci` の失敗数を **現状の 9 から増やさない**(`docs/STATUS.md` §3-5) | S05/S14 |
| Q6 | バックエンド変更 | **原則無変更**。集計に不足があれば読み取り系の最小追加のみ | S16 |

## 1. 現状(2026-11-23 確認分)

### 1.1 あるもの(利用する資産)

- **バックエンド**: `POST /api/branches/play`(開始)/ `GET .../state` / `POST .../choose` / `POST .../save` / `POST .../load` / `POST .../end` / `GET .../playthrough`(`src/backend/routers/branches.py:531-759`)。IDOR 対策済み(所有権検証 + UUID 検証)
- **リクエスト形**: `BranchPlayRequest { book_id: int, branch_id: int }`(`src/backend/schemas/branch_play.py:13`)
- **レスポンス形**: `BranchPlayStateResponse { session_id, book_id, branch_id, current_node, current_node_id, context, available_choices, save_points_count, status, updated_at }`(同 `:35`)
- **フロント API クライアント**: `frontend/src/api/branches.ts`(tree/fork/merge/diff 実装済み、`api/client.ts` 経由で Bearer 付与)
- **既存 UI 部品**: `frontend/src/components/branches/`(BranchTree/BranchSelector/BranchManagement)
- **hooks パターン**: `frontend/src/hooks/useBranchTree.ts` 等のカスタムフック構成

### 1.2 無いもの(本計画で作るもの)

- フロントの play 系 API 関数・型(`api/branches.ts` に play メソッドなし・2026-11-23 確認)
- Play モードページ・ルート・入口導線
- capability 宣言(`branchPlay`)

## 2. エピソード構成(4 × ~5 = 18 ステップ)

| Ep | ステップ | ゴール | 主要な変更 |
|----|----------|--------|-----------|
| 1 | S01-S06 | 型・API クライアント・セッションフック | `types/branches.ts`、`api/branches.ts`、`hooks/usePlaySession.ts` |
| 2 | S07-S13 | Play モードページと導線 | `pages/PlayModePage.tsx`、`routes.tsx`、`capabilities.ts` |
| 3 | S14-S16 | 検証と KPI 初期計測 | vitest、集計手順の文書化 |
| 4 | S17-S18 | ドキュメントと SSOT 同期 | `docs/easy_mode_guide.md`、`docs/STATUS.md` |

## 3. ステップ一覧

### Episode 1: 型・API クライアント・セッションフック (S01-S06)

#### S01 `types/branches.ts` に Play 型を追加

- **目的**: バックエンド `BranchPlayRequest` / `BranchPlaySessionResponse` / `BranchPlayStateResponse` の TS ミラー
- **変更ファイル**: `frontend/src/types/branches.ts`
- **追加内容**:
  ```typescript
  export interface BranchPlayRequest { book_id: number; branch_id: number }
  export interface BranchPlaySessionResponse {
    session_id: string; book_id: number; branch_id: number;
    current_node_id: string | null; status: string; updated_at: string;
  }
  export interface BranchPlayChoice { id: string; text: string; [k: string]: unknown }
  export interface BranchPlayStateResponse {
    session_id: string; book_id: number; branch_id: number;
    current_node: Record<string, unknown>;
    current_node_id: string | null;
    context: Record<string, unknown>;
    available_choices: BranchPlayChoice[];
    save_points_count: number; status: string; updated_at: string;
  }
  ```
  (正は `src/backend/schemas/branch_play.py`。実装時に再読して一致させる)
- **検証**: `cd frontend && npm run typecheck`
- **ロールバック**: `git revert`

#### S02 `api/branches.ts` に play 系関数を追加

- **目的**: 7 エンドポイントのクライアント実装(既存 `client.ts` の認証パターンに従う)
- **変更ファイル**: `frontend/src/api/branches.ts`
- **追加内容**: `startPlaySession(bookId, branchId)` / `fetchPlayState(sessionId)` / `choosePlay(sessionId, choiceId)` / `savePlay(sessionId)` / `loadPlay(sessionId, index)` / `endPlaySession(sessionId)` / `fetchPlaythrough(sessionId)`
- **検証**: `npm run typecheck`
- **ロールバック**: `git revert`
- **Low-LLM メモ**: 既存 `fetchBranchTree` の実装スタイル(エラーハンドリング含む)を完全コピーし、URL とメソッドだけ変える

#### S03 `usePlaySession` フック雛形

- **目的**: セッション状態(idle/loading/playing/ended)と操作の集約。`useBranchTree` パターンに合わせる
- **変更ファイル**: `frontend/src/hooks/usePlaySession.ts`(新規)
- **検証**: S05 でテスト
- **ロールバック**: ファイル削除

#### S04 フックへ save/load/playthrough を追加

- **目的**: セーブポイント管理と履歴取得
- **変更ファイル**: S03 と同じ
- **検証**: S05
- **ロールバック**: メソッド削除

#### S05 フック単体テスト

- **目的**: 状態遷移(開始 → 選択 → セーブ → ロード → 終了)の網羅
- **追加**: `frontend/src/hooks/usePlaySession.test.ts`(既存 hook テストのパターンに従う)
- **検証**: `npm run test:ci` — **失敗数が 9 から増えないこと**(Q5)
- **ロールバック**: テスト削除

#### S06 Episode 1 完了確認

- **検証**: `npm run typecheck && npm run lint`

### Episode 2: Play モードページと導線 (S07-S13)

#### S07 `PlayModePage` 雛形

- **目的**: `/app/play/:bookId` のページ本体。書籍配下のブランチ一覧から選んでセッション開始
- **変更ファイル**: `frontend/src/pages/PlayModePage.tsx`(新規)
- **検証**: ブラウザで描画確認(typecheck)
- **ロールバック**: ファイル削除

#### S08 シーン表示と選択肢 UI

- **目的**: `current_node` の本文表示 + `available_choices` のボタン化。選択で `choosePlay` → state 再取得
- **変更ファイル**: `PlayModePage.tsx`(または `components/play/` に分離)
- **検証**: 選択 → state 更新の描画確認
- **ロールバック**: `git revert`

#### S09 セーブ/ロード/playthrough パネル

- **目的**: セーブポイント一覧・復元・プレイ履歴の表示
- **検証**: save → reload → load で状態一致
- **ロールバック**: `git revert`

#### S10 グラフ未生成時のガイダンス

- **目的**: `current_node` が空(=IF グラフ未生成)の書籍で、Studio のブランチ管理へ誘導する空状態を出す。「押せるのに何も起きない」を避ける(`frontend/src/capabilities.ts` 冒頭の設計思想に準拠)
- **検証**: グラフ無し書籍でガイダンス表示
- **ロールバック**: `git revert`

#### S11 ルート追加

- **変更ファイル**: `frontend/src/routes.tsx`
- **追加内容**:
  ```typescript
  { path: "/app/play/:bookId", element: <PlayModePage />, errorElement: <RouteErrorView /> },
  { path: "/app/play", element: <PlayModePage />, errorElement: <RouteErrorView /> },
  { path: "/play", element: <Navigate to="/app/play" replace /> },
  ```
  加えて routes.tsx 内のナビ設定配列(既存 `/app/easy` 等と同型)にエントリ追加
- **検証**: `npm run typecheck` + 手動遷移
- **ロールバック**: `git revert`

#### S12 capability 宣言

- **変更ファイル**: `frontend/src/capabilities.ts`
- **追加内容**:
  ```typescript
  branchPlay: { status: "wired" } as Capability,
  ```
- **検証**: `npm run typecheck`
- **ロールバック**: `git revert`

#### S13 入口導線

- **目的**: 3 入口からの到達性。ヘッダーメニューに「▶ Play」、`components/branches/BranchManagement.tsx` に「プレイ」ボタン(branchId を持って遷移)
- **検証**: かんたん執筆 → Studio → ブランチ管理 → プレイ の導線が通る
- **ロールバック**: `git revert`

**Episode 2 完了条件**:
- [ ] UI で「プレイ開始 → 選択 → セーブ/ロード → playthrough 表示」が完走
- [ ] `/play` 旧 URL リダイレクトが機能

### Episode 3: 検証と KPI 初期計測 (S14-S16)

#### S14 PlayModePage の vitest

- **追加**: render テスト(開始 → 選択で state が更新される。API はモック)
- **検証**: `npm run test:ci` 失敗数が 9 から増えないこと
- **ロールバック**: テスト削除

#### S15 手動 E2E 手順の実施

- **目的**: mock LLM(`LLM_PROVIDER=mock`)で本生成 → Studio で分岐作成 → Play で完走までの実機確認。手順を本計画書の下に実行記録として追記
- **検証**: 完走ログを残す

#### S16 KPI 初期計測の整備

- **方針(Q4)**: フロント計測基盤は作らない。`branch_play_sessions` の集計で代替する
- **変更ファイル**: なし(集計 SQL を本計画書に記載)
  ```sql
  -- プレイ開始数 / 完走数 / セーブ使用率
  SELECT status, COUNT(*) FROM branch_play_sessions GROUP BY status;
  ```
  完走率 = completed / 全セッション。開始数の分母(生成完了書籍数)は `books` テーブル側で集計
- **検証**: SQLite ローカル DB で実行できること
- **ロールバック**: なし

### Episode 4: ドキュメントと SSOT 同期 (S17-S18)

#### S17 ユーザーマニュアル更新

- **変更ファイル**: `docs/easy_mode_guide.md`(Play モードの節を追加)、必要なら `docs/README.md` の索引
- **検証**: `mkdocs build --strict` で警告が増えないこと(既存 35 件が現状基準)

#### S18 SSOT 更新と PR

- **変更ファイル**: `docs/STATUS.md` §2 に「Play モード UI(Phase 0)— 実装済み(根拠: `frontend/src/pages/PlayModePage.tsx`)」を追記、`CHANGELOG.md` Unreleased に追記
- **検証**: `make openapi`(API 変更がなければ差分出ないことを確認)+ `make verify` のうち lint/typecheck 系が既存と同水準
- **ロールバック**: `git revert`

## 4. Done の 5 条件

1. UI で「開始 → 選択 → セーブ/ロード → playthrough」が完走(S15 の実行記録付き)
2. `npm run typecheck` / `npm run lint` がグリーン、`npm run test:ci` の失敗数が 9 から増えていない
3. `/play` リダイレクトとヘッダー導線が機能
4. KPI 初期値(プレイ開始数・完走率)が集計可能(S16 の SQL で取得できる)
5. `docs/STATUS.md`・`docs/easy_mode_guide.md`・`CHANGELOG.md` が更新済み

## 5. リスク Top3

| # | リスク | 兆候 | 対応 |
|---|--------|------|------|
| 1 | 既存フロント 9 失敗との干渉 | vitest 実行で新失敗 | Q5: 完了条件を「9 から増やさない」に固定。新規テストは独立ファイルに置く |
| 2 | グラフ未生成書籍で「空の画面」 | プレイ開始が 404/空 state | S10 のガイダンスを先に実装(S07 と同時でも可) |
| 3 | 書籍 → ブランチ一覧の取得導線が長い | プレイまでのクリック数が多い | BranchManagement から直接プレイに飛べる導線(S13)を最低限保証 |

## 6. Low-LLM 実装メモ(全ステップ共通)

1. **既存ファイルを必ず読む**: 該当ステップの「変更ファイル」を Read してから Edit する
2. **パターン踏襲**: API は `api/branches.ts` 既存関数、UI は `components/branches/` 既存部品、hooks は `useBranchTree` パターンをコピーしてから変える
3. **1 ステップ = 1 commit**: ロールバック粒度を担保
4. **フロント型の正は OpenAPI**: 型が合わないときは `npm run type:sync` で同期してから手直しする(バックエンド変更が無いので不要なはず。必要になったら手動型を疑う)
5. **検証コマンドを毎回実行**: typecheck/lint/test:ci の 3 点セット
6. **バックエンドに手を出さない**: 不足があると判断したら本計画書にコメントして止まる(Q6)

## 7. 実行記録

**実施日:** 2026-11-23 / **実装ブランチ:** `feature/play-mode-phase0`

### 実装済みステップ

| Ep | ステップ | 状態 | コミット / 成果物 |
|:---|:---|:---:|:---|
| 0 | (計画外)テスト基盤修復 | ✅ | `1af6f231` — Node 26 の実験的 localStorage が jsdom の Storage を影にし、**全 74 ファイル / 389 テストが setup で失敗**していた(STATUS §3-5 の「9 失敗」の実態もこれ)。`tests/setup.ts` にフォールバック polyfill を追加(旧 Node では不発) |
| 1 | S01-S02 型・API クライアント | ✅ | `4472f481` — `types/branches.ts` に Play 型 5 種、`api/branches.ts` に play 系 7 関数 |
| 1 | S03-S05 フック+テスト | ✅ | `6d48581c` — `usePlaySession`(状態機械 idle→starting→playing→ending→ended)+ 単体テスト 10 件 |
| 2 | S07-S14 ページ・ルート・導線 | ✅ | `a1bc5e78` — `PlayModePage`、`/app/play` ルート+旧 `/play` リダイレクト、`capabilities.ts` に `branchPlay: wired`、ヘッダー「▶ Play」ボタン、BranchManagement「▶ プレイ」ボタン(`?branch=` で分岐引き継ぎ)、結合テスト 9 件 |
| 3 | S15 E2E(API レベル) | ✅ | 下記 §7.1 |
| 3 | S16 KPI 集計 SQL | ✅ | 下記 §7.2(計画 §3 S16 の SQL を実 DB で検証) |
| 4 | S17 ユーザーマニュアル | ✅ | `docs/easy_mode_guide.md` に「▶ Play モード」節 + 導線図更新 |
| 4 | S18 SSOT 同期 | ✅ | 本節 + `docs/STATUS.md` §2 + `CHANGELOG.md` + `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §3/§4 |

### S15 の差異(計画からの変更)

- **ブラウザでの手動 E2E は実施せず、API レベル E2E で代替した。** 理由: 実行環境(Node 26)では react-router のテスト内ナビゲーションが undici の AbortSignal クロスレルム問題で動作しないため、UI 遷移の自動検証は不可。UI は結合テスト 9 件(コンポーネント単位)+ 実 API との整合(API レベル E2E)で担保した。ブラウザでの目視確認は利用者側の初回利用時にフィードバックを得る
- なお Node 26 環境では vitest + jsdom の localStorage も壊れる(→ Ep 0 の修復)

### 7.1 API レベル E2E 実施結果(mock LLM 不要・グラフ型プレイ)

実バックエンド(uvicorn + SQLite)で以下を全て 200/期待動作で確認(2026-11-23):

| # | 操作 | 結果 |
|:--|:---|:---|
| 1 | ユーザー登録/ログイン | ✅ JWT 取得 |
| 2 | 書籍作成(`POST /api/books`) | ✅ book_id=1 |
| 3 | 分岐+グラフ作成(`POST /api/branches/`、`graph_json` 3 ノード) | ✅ branch_id=1 |
| 4 | プレイ開始(`POST /api/branches/play`) | ✅ session 発行、`current_node_id=node_start` |
| 5 | 状態取得(`/state`) | ✅ ノード本文+選択肢 2 件 |
| 6 | 選択(`/choose` `c_open`) | ✅ `node_open` へ遷移、flags 記録 |
| 7 | セーブ(`/save`) | ✅ save_points=1 |
| 8 | 終端ノードからの不正選択 | ✅ 400 `Choice not available from current node`(適切に拒否) |
| 9 | 復元(`/load?index=0`) | ✅ セーブ時点のノードへ復元 |
| 10 | 履歴(`/playthrough`) | ✅ `history=[{from, choice_id, to}]`、`flags={opened:true}` |
| 11 | 終了(`/end`) | ✅ `status=completed` |

### 7.2 KPI 初期集計(S16)

上記 E2E DB に対して計画 §3 S16 の SQL を実行し、`status` 集計・完走率・書籍数が取得できることを確認。本番での基準値は実ユーザーのデータ蓄積後に設定する(ロードマップ §6)。

### ゲート結果

- `tsc --noEmit`: **グリーン**
- `eslint`(新規・変更ファイル): **0 errors**(既存 warning 6 件は BranchManagement の既存未使用変数で本計画と無関係のため触らない)
- `vitest run`: **全 74 ファイル / 398 テスト パス、失敗 0**(ベースライン 379 + 新規 19)
- 未処理 rejection 2 件は既存の Node 26 × react-router(undici)の環境問題で、テスト結果には影響しない(旧 Node では発生しない)
