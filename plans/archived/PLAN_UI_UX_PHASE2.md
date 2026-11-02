# PLAN: UI/UX Remediation Phase 2（残存タスク対応）

作成日: 2026-10-01
前提: [`PLAN_UI_UX_REMEDIATION.md`](PLAN_UI_UX_REMEDIATION.md) 完了（S1〜S12 / 138 tests pass）
対象: `autonovel/frontend` + 一部 `autonovel/src/backend`

---

## 0. 背景

Phase 1 で「押したボタンは必ず何かが起きる」「メッセージは嘘でない」を達成した。
残る課題は **機能欠落（データが保存されない）** と **技術債（孤児コード）** と **表示不具合（テーマ不整合）** に分かれる。

本計画では **R1（前回の実装が持ち込んだ負債）を最優先** で解消し、その後に影響範囲の広い順に着手する。

---

## 1. 残存タスク一覧

| # | タスク | 現状 | 分類 | 推奨順序 |
|---|---|---|---|---|
| **R1** | `GET /api/multimedia/images/{scene}` が**存在しない** | `StudioWorkspace` が叩くが backend に `images`/`image_url` endpoint が**ゼロ**。常に404→空状態 | 負債（Phase1 持ち込み） | **1** |
| **R2** | 章の追加/削除/並び替えが永続化されない | `ChapterOutlineTree` は `setChapters` のみ。取得 GET はあるが保存 API が無い | 機能欠落 | **2** |
| **R3** | Wizard 執筆分がサーバに残らない | localStorage 退避のみ。`POST /api/episodes/chapters/import` 未活用 | 機能欠落 | **2** |
| **R4** | 孤児 state の二重管理 | `NovelContext` の `selectedStyleId` 等4つが localStorage に書くだけで **context value に未公開**。GeneratePanel は同名ローカル state を別に持つ | 技術債 | **3** |
| **R5** | 空実装ハンドラ | `handleRunDistill` / `handleApplyCustomStyle` が `// Implementation placeholder` | 技術債 | **3** |
| **R6** | 死んだファイル・props | `WizardStep.tsx`（旧ウィザード削除後に孤児）、`SimpleModePanel` の未使用 props 5個 | 技術債 | **3** |
| **R7** | 入力欄のテーマ不整合 | `.input`/`.textarea` が暗背景ハードコード。ライト/セピアでも黒 | 表示不具合 | **4** |
| **R8** | モバイルUIのテーマ非対応 | `MobileBottomNav` が `bg-slate-950` 固定 | 表示不具合 | **4** |
| **R9** | ポーリング負荷 | `POLL_INTERVAL_MS = 100`（10req/s）。内部ステータスがそのままUIに出る | 性能/表示 | 5 |
| **R10** | 全量テストがOOM | `vitest run` 全体が heap 枯渇 | 開発環境 | 5 |

---

## 2. 優先順位の根拠

```
R1 → (R2 + R3) → (R4 + R5 + R6) → (R7 + R8) → (R9, R10)
```

- **R1 を最初に**: Phase 1 の自分の実装で持ち込んだ負債であり、放置すると「壊れたまま出荷する」状態になる。先に片付ける。
- **R2/R3 を R4 より前**: R2/R3 の永続化の設計判断を R4 の解消と共有できる。**R4 を先にやると、あとで作り直すはめになる。**
- **R7/R8 をまとめる**: 同じ「CSS 変数化の同種問題」。`--surface-*` トークンは定義済みなので、1トークン追加で両方が直る。
- **R9/R10 は独立**: 他の修正に影響しないため最後に回してよい。

---

## 3. 各タスクの実装方針

### R1. シーン画像 API の実体化（最優先・1日）✅ **完了**

**現状の問題**: [`StudioWorkspace`](autonovel/frontend/src/components/studio/StudioWorkspace.tsx) が `GET /api/multimedia/images/{scene}` を叩くが、backend に存在しない。

**実装結果**:

- バックエンド: [`illustrations.py`](autonovel/src/backend/routers/illustrations.py) に `GET /images/{book_id}/{scene_name}` を追加
  - 既存の `Illustration` テーブル（`image_url` 永続済み）から取得
  - **IDOR 防止**として `verify_book_ownership` を必ず呼ぶ
  - `image_url` が空（prompt 生成のみ）の行は「画像あり」と見なさない
  - シーン名が `prompt` に含まれれば一致、無ければ最新へフォールバック
- フロント: [`illustrations.ts`](autonovel/frontend/src/api/illustrations.ts) に `fetchSceneIllustration()` を新設し、[`StudioWorkspace`](autonovel/frontend/src/components/studio/StudioWorkspace.tsx) から利用
  - 契約: `{"found": bool, "image_url": str|null, "illustration_id": int|null}`
  - 404 でも例外にせず `undefined`（未生成と障害を混同しない）

**検証結果**:

| 対象 | 結果 |
|---|---|
| `tests/unit/backend/test_illustrations_scene_image_api.py` | **5 passed** |
| `tests/unit/uiux/sceneImageApi.test.ts` | **6 passed** |
| `npx tsc --noEmit` | エラー **0** |
| `tests/components` + `tests/integration` + `tests/unit/uiux` | **144 passed**（回帰 0 件） |

**完了条件**: ✅ 実在する endpoint を叩いており、`found:false` で空状態表示になる

### R2 + R3. チャプター UPSERT API の新設（3〜5日）✅ **完了**

**実装結果**:

- 調査で判明: `ChapterRepository.create_chapter()` は既に内部で upsert していた
  （既存行があれば更新、無ければ作成）。よって **新規の保存ロジックは不要**で、
  薄い API を1本公開するだけの実装になった。
- バックエンド: [`episodes.py`](autonovel/src/backend/routers/episodes.py) に
  - `PUT /api/episodes/chapters/{book_id}/{ep_num}`（Upsert）
  - `DELETE /api/episodes/chapters/{book_id}/{ep_num}`（削除）
  - いずれも `verify_book_ownership` で IDOR 防止
- フロント: [`chapters.ts`](autonovel/frontend/src/api/chapters.ts) を新設
  - R2: [`ChapterOutlineTree`](autonovel/frontend/src/components/studio/ChapterOutlineTree.tsx) の
    追加/削除/改名/並び替えをすべて永続化に接続（**楽観更新＋失敗時は必ず通知**）
  - R3: [`WizardWorkflowPage`](autonovel/frontend/src/pages/WizardWorkflowPage.tsx) の
    執筆完了時にサーバへ保存（localStorage 退避はオフライン用に残置）

**検証結果**: `tests/unit/uiux/chapterPersistence.test.ts` 6 passed

**完了条件**: ✅ リロードしても章の追加/削除/並び替えと Wizard 執筆分が保持される

### R4 + R5 + R6. 技術債の掃除（1日）✅ **完了**

**実装結果**:

- **R4**: [`NovelContext.tsx`](autonovel/frontend/src/context/NovelContext.tsx) から孤児4つと
  localStorage 同期Effect を削除（約90行）。実際の状態は GeneratePanel のローカル state が保持。
- **R5**: `handleRunDistill` / `handleApplyCustomStyle`（`// Implementation placeholder`）を削除。
- **R6**: 孤児ファイル `WizardStep.tsx` を削除。
  `SimpleModePanel` / `OrchestratedModePanel` の未使用 props 計14個も削除。

**完了条件**: ✅ `tsc --noEmit` エラー0、既存テスト0回帰

### R7 + R8. テーマ対応（2日）✅ **完了**

**実装結果**:

- `--input-bg` トークンを追加し、dark / light / sepia の3テーマに定義。
  `.input` / `.textarea` / `.select` は `var(--input-bg)` を使うように変更（ハードコード暗色を廃止）。
  `select` のドロップダウン（`option`）も追従。
- `MobileBottomNav` / `MobileQuickActionBar` の固定ダーク色
  （`bg-slate-950` / `bg-slate-900` / `text-slate-*`）を
  `var(--surface-1|2)` / `var(--text-main)` / `var(--accent-purple)` に置換。

**検証結果**: `tests/unit/uiux/themeConsistency.test.ts` 4 passed

**完了条件**: ✅ ライト/セピア/ダーク全テーマで入力欄・モバイルナビの可読性が保たれる

### R9. ポーリング改善（1日）✅ **完了**

**実装結果**:

- ポーリング間隔を `[100, 300, 1000]ms` の段階式に変更（等間隔 100ms の 10req/s をやめ、
  待ち時間に応じて負荷を下げる）。
- `humanizeStatus()` を導入し、内部値（`running` / `queued` など）を
  ユーザー向け文言（🪄 AIが執筆しています。このままお待ちください… 等）に変換。
  ユーザーが「これは失敗か？」と誤解する原因を解消。
- タイムアウト文言も 60秒→5分 に合わせて更新。

### R10. テスト安定化（半日）✅ **完了**

**実装結果**:

- [`vite.config.ts`](autonovel/frontend/vite.config.ts) の test 設定に
  `pool: "forks"` と `poolOptions.forks`（`minForks:1 / maxForks:4 / isolate:true`）を明示。
  jsdom のメモリが単一プロセスに集中して heap 枯渇（OOM）していたのを解消。

---

## 4. 回帰防止テスト

各タスクに対応する新規/既存テストで状態固定する。

| タスク | テスト内容 | ファイル |
|---|---|---|
| R1 | 実在 endpoint を叩く／404 ではなく空状態になる | `tests/unit/uiux/sceneImageApi.test.tsx` |
| R2 | 章操作が API 呼びに対応／失敗時ロールバック | `tests/unit/uiux/chapterPersistence.test.tsx` |
| R3 | Wizard 執筆分がサーバに送られる | `tests/unit/uiux/wizardChapterSave.test.tsx` |
| R4 | context に孤児 state が残っていない | `tests/unit/uiux/noOrphanState.test.tsx` |
| R5/R6 | 空実装ハンドラ・孤児ファイルが存在しない | 静的チェック or `legacyWizardRemoved` 拡張 |
| R7/R8 | テーマ切替で入力欄が追従する | `tests/unit/uiux/themeConsistency.test.tsx` |
| R9 | 進捗文言が内部ステータスを露出しない | `tests/unit/uiux/generationProgress` 拡張 |

**各ステップ完了時に**: `npx tsc --noEmit`（エラー0）と既存回帰テスト（`tests/components`, `tests/integration`, `tests/unit/uiux`）が全て pass であることを確認する。

---

## 5. 全体の DoD

- `npx tsc --noEmit` エラー0
- `npx vitest run tests/components tests/integration tests/unit/uiux` が全 pass（新規回帰0）
- R1〜R8 が完了（または明確に次フェーズ送りとして文書化）
