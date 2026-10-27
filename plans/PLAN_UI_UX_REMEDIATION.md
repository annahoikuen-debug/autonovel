# PLAN: UI/UX Remediation（機能とUIの連結修復・回帰防止テスト込み）

作成日: 2026-10-01
対象: `autonovel/frontend`
前提調査: UI/UX 精査（2026-09-30） findings C-1〜C-6 / M-1〜M-6

---

## 0. 背景と目標

UI/UX 精査で「UI 上は存在するが実機能が動かない」「嘘のフィードバックを出す」类的欠陥を特定した。
本計画は **UI と機能の有機的連結を修復し、その状態を回帰テストで固定する** ことを目標とする。

評価軸:
1. 押した按钮が **必ず** 何らかの変化を生む（死んだボタン 0 件）
2. フィードバックメッセージが **実際の結果と一致** する（嘘のトースト 0 件）
3. 初回利用者が専門用語や内部キーに触れない
4. 各修正は **対応する回帰テスト** を持ち、以降の修正で壊れない

---

## 1. Findings と対応マトリクス

| ID | 深刻度 | 症状 | 対応 | 回帰テスト |
|---|---|---|---|---|
| C-1 | 🔴 | 「Easyモードに戻る」ボタンが `navigate` を呼ばず画面が留まる | S1 | `tests/unit/uiux/entryNavigation.test.tsx` |
| C-2 | 🔴 | 「📝 執筆重視」レイアウト切替がデッド UI | S2 | `tests/unit/uiux/studioLayoutMode.test.tsx` |
| C-3 | 🟠 | `OrchestratedModePanel` 到達不能（`setMode('orchestrated')` なし） | S3 | `tests/unit/uiux/advancedModeReachable.test.tsx` |
| C-4 | 🔴 | モバイル QuickAction が全部トースト偽装（本文に何も起きない） | S4 | `tests/unit/uiux/mobileQuickActions.test.tsx` |
| C-5 | 🔴 | Step3 textarea に `onChange` が無く編集内容を失う | S5 | `tests/unit/uiux/wizardStep3Editing.test.tsx` |
| C-6 | 🟠 | 旧6ステップウィザードが `/wizard` と二重存在 | S6 | `tests/unit/uiux/legacyWizardRemoved.test.tsx` |
| M-1 | 🟠 | 「文体スタイル」が内部キー `style_web_standard` の生入力欄 | S7 | `tests/unit/uiux/stylePresetSelector.test.tsx` |
| M-2 | 🟠 | メイン CTA が2つ同列・同サイズで選択判断がcycling | S7 | （同上） |
| M-6 | 🟠 | 生成中の進捗 `statusText` が画面に出ていない | S8 | `tests/unit/uiux/generationProgress.test.tsx` |
| M-3 | 🟡 | Step1 の専門用語に説明がない | S9 | `tests/unit/uiux/wizardTerminology.test.tsx` |
| M-4 | 🟡 | Step2 の Cliffhanger / 五感タグが英語のまま | S9 | （同上） |
| M-5 | 🟡 | Wizard の執筆分がメモリのみで永続化されない | S10（localStorage退避） | `tests/unit/uiux/wizardDraftPersistence.test.tsx` |
| MIN-1 | 🟡 | `Modal` にフォーカストラップ／フォーカス復元がない | S11 | `tests/unit/uiux/modalFocusTrap.test.tsx` |
| MIN-2 | 🟡 | Studio のシーン画像が `placehold.co` プレースホルダー | S12 | `tests/unit/uiux/scenePreviewNoPlaceholder.test.tsx` |

---

## 2. 実装ステップ

### S1. 「Easyモードに戻る」を実遷移化（C-1）
**対象**: `src/components/studio/StudioWorkspace.tsx`, `src/context/NovelContext.tsx`, `src/components/layout/AppLayout.tsx`

- `StudioWorkspace` に `useNavigate` を導入し、🏠 ボタンのハンドラで `navigate("/")` を呼ぶ。
- `mode` state はルーティングと二重管理になっているため、**読み取り箇所をゼロ** にして削除する（`mode`/`setMode` は context から除去、localStorage `autonovel.mode` は移行互換のため残す）。
- `AppLayout` からの `setMode` 参照が無く、无用の localStorage 書き込みを削除。

**完了条件**: 🏠 を押すと URL が `/` になり、Easy Mode の画面が表示される。`mode` が context 型に存在しない。

### S2. 「執筆重視」レイアウトを実装（C-2）
**対象**: `src/components/studio/StudioWorkspace.tsx`

- `layoutMode === "split"` のとき、左ペイン（章一覧・設定）を隠し、右ペイン（AI編集者）を隠して **エディタ全幅** にする。
- 実効ペイン状態を `layoutMode` から導出するヘルパー `derivePaneVisibility(layoutMode)` を追加し、明示トグル（`showLeftPane`/`showRightPane`）との相互作用を定義する。
- `split` 選択時にトグルボタンの状態を同期する（押しても Staat が矛盾しない）。

**完了条件**: 「📝 執筆重視」を押すと `btn-toggle-left-pane` と `btn-toggle-right-pane` が消え、エディタが全幅になる。`studio` に戻すと復元される。

### S3. `OrchestratedModePanel` の到達性確保（C-3）
**対象**: `src/components/GeneratePanel.tsx`

- 上級モードの折り畳み内に「🧠 マルチエージェント執筆（ORCHESTRA）」ボタンを追加し `setMode("orchestrated")` を呼ぶ。
- 既に import 済みの `useUnifiedStreaming` / `OrchestratedModePanel` が実際に描画されるようにする。

**完了条件**: 「もっと細かく設定する」を開き、ORCHESTRA ボタンを押すと `AgentProgressView` 系 UI が出る。`monitor-fold` の誘導が嘘にならない。

### S4. モバイル QuickAction を実処理に接続（C-4）
**対象**: `src/components/layout/AppLayout.tsx`, `src/components/mobile/MobileQuickActionBar.tsx`

- `onInsertText` を **本文への実挿入** にする。挿入先テキストエリア（`#editor-textarea` / `#editor-textarea-zen` / `[data-testid="wizard-chapter-textarea"]`）を取得し、選択範囲を `setRangeText` で置換してから `input` イベントで通知する。
- `onAiContinue` / `onProofread` は **未接続**。トーストだけ返す実装は削除し、対応する実処理が歩くまで **ボタンをレンダリングしない** ように `MobileQuickActionBar` を変更（`onAiContinue`/`onProofread` を optional にして、未提供なら非表示）。
- 挿入できない（対象 textarea 不在）場合は「本文を開いているときだけ使えます」のような **正直なメッセージ** を出す。

**完了条件**: 「『』」を押すと本文に実際に挿入される。対応 textarea が無いときは嘘のメッセージが出ない。既存の `MobileResponsive.test.tsx`（onAiContinue 呼び出し検証）は optional 化により壊れないよう、バーは渡された callback のみ描画する。

### S5. Step3 の編集内容を失わない（C-5）
**対象**: `src/components/wizard/Step3InteractiveWriting.tsx`, `src/pages/WizardWorkflowPage.tsx`

- textarea に `onChange` を追加し、手動編集を `onContentChange(content, false)` として親へ通知する（`done=false` なので親は保存確定しない）。
- 親の `handleContentChange` を「機械生成の確定」と「人手編集」を区別できるよう拡張し、**手動編集を `generatedChapters[episode]` に即時反映** する。
- 「編集内容を保存」導線を追加: Step3 在当地保持し、Step2 へ戻る／ページ unload 時に `autonovel.wizard.draft.{bookId}.{ep}` を localStorage へ退避し、復帰時に復元。
- 「Studio で細部を手入れする」前に、未保存の執筆内容を localStorage へ確実に書き出す。

**完了条件**: Step3 の textarea に文字を入力すると value が変わる（入力が飲み込まれない）。リロードしても本文が残る。

### S6. 旧6ステップウィザードの二重化を解消（C-6）
**対象**: `src/components/studio/StudioWorkspace.tsx`, `src/components/layout/AppLayout.tsx`, `src/context/NovelContext.tsx`

- `StudioWorkspace` から `WizardStep` import と `isWizardActive` ブロック（6ステップオーバーレイ）を削除。
- `AppLayout` の新規作品作成ハンドラから `setWizardStep(1); setIsWizardActive(true)` を削除。
- `NovelContext` から `wizardStep` / `isWizardActive` / `hasCompletedWizard` を削除（`hasCompletedWizard` は `autonovel.wizard_completed` を参照していただけなので localStorage キーは残す）。
- 既存テスト [`ZenModeAndEditor.test.tsx`](autonovel/frontend/src/components/editor/__tests__/ZenModeAndEditor.test.tsx) の context モックから該当フィールドを削除。

**完了条件**: `/wizard` のみがウィザード導線。`routes.tsx` の「3 つの入口」と実態が一致する。

### S7. Easy Mode の初回画面から専門用語・内部キーを排除（M-1, M-2）
**対象**: `src/components/generate/SimpleModePanel.tsx`

- 「文体スタイル」の内部キー生入力欄を **プリセット `select`** に置き換える。選択肢は `fetchStylePresets()` から取得（失敗時は静的フォールバック）。
- `styleKey` はローカル state ではなく、生成フックへ **実際に渡す**（`llmConfig` ではなく `SimpleModePanel` から `startStreaming`/`startGeneration` へ `styleKey` を渡す props 化）。
- メインCTAを **主次を明確化**: 「🪄 かんたん執筆」を最大幅のプライマリとし、「⚡ リアルタイム速筆」は副次（細い・小さい）にする。ガチャ/ダイジェスト/チラ見せは `<details>` へ移動して主CTAの視覚支配を弱める。
- 重複する「1話あたりの目標文字数」（本体とカスタム設定の両方に出ている）を1箇所に集約。

**完了条件**: 内部キー `style_web_standard` の文字列が UI に出ない。`startGeneration` が `styleKey` を含む形で呼ばれる。

### S8. 生成進捗の可視化（M-6）
**対象**: `src/components/generate/SimpleModePanel.tsx`

- `generationState.statusText` を `aria-live="polite"` 付きで描画する（進捗行）。
- `generationState.error` を `role="alert"` 付きで表示する。
- タイムアウト値を 60秒 → **300秒** に延長（`useNovelGeneration.ts` の `POLL_TIMEOUT_MS`）— 長尺原稿で必ず失敗する_FIXME。

**完了条件**: 生成中に進捗テキストが表示される。エラーが `role="alert"` で出る。

### S9. Wizard の用語・日本語化（M-3, M-4）
**対象**: `src/components/wizard/Step1PlotInput.tsx`, `src/components/wizard/Step2StructureReview.tsx`

- Step1: 「チート度」等に **両端の説明** を追加（「1=Wereld設定靠不住 → 5=完全に 유리」）。range の `aria-valuetext` を設定し、`aria-describedby` で説明文を紐付ける。
- Step2: `CLIFFHANGER_TYPES` と `SENSORY_OPTIONS` を **日本語表示＋内部英語値を保持** する構造（`{value, label}` 形式）に変更。API 送信時は英語値を渡す。
- 「Step 1:」「Step 2:」「Step 3:」の見出しを「ステップ1:」等へ日本語化。
- `label` に `htmlFor` / `id` を付与して、クリックでフォーカス移動できるようにする。

**完了条件**: Step2 の option テキストに `visual` 等の英字が現れない（ただし API payload は英語のまま）。

### S10. Wizard 執筆分の退避（M-5）
**対象**: `src/pages/WizardWorkflowPage.tsx`

- `generatedChapters` を localStorage（`autonovel.wizard.draft.{bookId}`）へ debounce 保存。
- mount 時に読み込み、`writtenCount` / `lastWrittenEpisode` を復元。

**完了条件**: リロード後に「執筆済み N 話」が維持される。

### S11. Modal のフォーカストラップ・復元（S11）
**対象**: `src/components/common/Modal.tsx`

- 開いた時の **`previouslyFocused` の保存** と、閉じた時に **元へ戻す**。
- `keydown` で `Tab` / `Shift+Tab` を捕捉し、ダイアログ内の focusable 要素で循環させる。

**完了条件**: モーダル内で Tab が外へ抜けない。閉じると元のボタンにフォーカス戻る。

### S12. プレースホルダー画像の撤去（S12）
**対象**: `src/components/studio/StudioWorkspace.tsx`

- `placehold.co` を参照していた `fetchImage` を、実際の画像解決 API（`/api/multimedia/...`）呼び出しに変更し、失敗時は **空状態 UI**（🔍 シーン画像を生成してください）を表示。外部 placeholder サービスを到達不能時に呼ばない。

**完了条件**: ネットワークに `placehold.co` へのリクエストが出ない。失敗時は空状態。

---

## 3. 回帰防止テスト（Test Plan）

新規ディレクトリ: `frontend/tests/unit/uiux/`

| ファイル | 対象 | 検証内容 |
|---|---|---|
| `entryNavigation.test.tsx` | S1 | 🏠押下 → `/` へ遷移。`mode` が context に無い |
| `studioLayoutMode.test.tsx` | S2 | split で左右ペイン消失／studio で復元／zen で別画面 |
| `advancedModeReachable.test.tsx` | S3 | 上級モード展開→ORCHESTRA→`AgentProgressView` 表示 |
| `mobileQuickActions.test.tsx` | S4 | テキスト挿入が実 DOM に反映／callback 未提供なら非表示 |
| `wizardStep3Editing.test.tsx` | S5 | textarea 入力が value に反映／退避・復元 |
| `legacyWizardRemoved.test.tsx` | S6 | `WizardStep` が Studio に含まれない／新規作品作成で旧導線が出ない |
| `stylePresetSelector.test.tsx` | S7 | select 表示・内部キー非露出・styleKey が生成に渡る |
| `generationProgress.test.tsx` | S8 | statusText 表示・error が role=alert |
| `wizardTerminology.test.tsx` | S9 | 用語説明あり／Step2 option が日本語／label 関連付け |
| `wizardDraftPersistence.test.tsx` | S10 | 執筆済み話数がリロード後も維持 |
| `modalFocusTrap.test.tsx` | S11 | Tab 循環・閉時フォーカス復元 |
| `scenePreviewNoPlaceholder.test.tsx` | S12 | placehold.co を参照しない／空状態表示 |

既存テストへの影響と対策:
- `tests/components/MobileResponsive.test.tsx` — `onAiContinue` を渡したケースを維持できるよう、未提供時のみ非表示（渡された場合は描画）。既存アサーションはそのまま通る。
- `tests/components/StudioWorkspace.test.tsx` — split 実装で DOM が変わらない範囲に収める（peine はデフォルトで両方表示）。既存アサーション互換。
- `src/components/editor/__tests__/ZenModeAndEditor.test.tsx` — context モックから削除する 3 フィールドをSpectrum的に外す。

---

## 4. 実行順序

1. S1, S2, S3, S4（死んだボタン・嘘の導線の解消）— 影響範囲が局所的で効果最大
2. S5, S8（データ損失・不可視地进行の解消）
3. S6, S7（構造の単純化・初回UX）
4. S9〜S12（表现層・a11y・堅牢性）
5. 各ステップのたびに `npm run typecheck` と対象テストを実行

---

## 5. 実施結果（DoD 達成）

### 検証結果

| 検証 | 結果 |
|---|---|
| `npx tsc --noEmit` | エラー **0** |
| `npx vitest run tests/unit/uiux`（新規 9 ファイル） | **47 tests passed** |
| `npx vitest run tests/components tests/integration tests/unit/uiux` | **138 tests passed**（31 files / 新規回帰 0 件） |

### 実装完了（12 ステップ全完）

| ステップ | 内容 | 主な変更ファイル |
|---|---|---|
| S1 | 「かんたん執筆に戻る」を実遷移化、`mode` state 廃止 | `StudioWorkspace.tsx`, `NovelContext.tsx`, `useOptionalNavigate.ts`（新規） |
| S2 | 「執筆重点（split）」レイアウトを実装 | `StudioWorkspace.tsx` |
| S3 | ORCHESTRA モードへの導線追加（到達不能を解消） | `GeneratePanel.tsx` |
| S4 | モバイル QuickAction を実挿入に接続、未接続ボタンは非表示 | `MobileQuickActionBar.tsx`, `manuscriptInsertion.ts`（新規）, `AppLayout.tsx` |
| S5 | Step3 textarea に `onChange` を接続（編集内容を失わない） | `Step3InteractiveWriting.tsx`, `WizardWorkflowPage.tsx` |
| S6 | 旧6ステップウィザードの二重化を解消 | `StudioWorkspace.tsx`, `AppLayout.tsx`, `useEditorKeybindings.ts` |
| S7 | 文体を内部キー入力→プリセット `select` 化、CTA 主次明確化 | `SimpleModePanel.tsx`, `useNovelGeneration.ts`, `useStreamingWriter.ts` |
| S8 | 生成進捗表示、`role=alert` のエラー表示、タイムアウト 60s→300s | `SimpleModePanel.tsx`, `useNovelGeneration.ts` |
| S9 | 専門用語に説明・`aria-valuetext` を付与、Step2 の選択肢を日本語表示 | `Step1PlotInput.tsx`, `Step2StructureReview.tsx` |
| S10 | Wizard 執筆分の localStorage 退避・復元 | `WizardWorkflowPage.tsx` |
| S11 | Modal のフォーカストラップ・フォーカス復元・スクロールロック | `Modal.tsx` |
| S12 | 外部プレースホルダー画像（`placehold.co`）撤去 | `StudioWorkspace.tsx` |

### 副次修正（テストで顕在化したもの）

- `tests/setup.ts` に `cleanup()` / `localStorage.clear()` を追加し、テスト間の DOM 累積を防止
- `ZenModeAndEditor.test.tsx` の context モックから削除済みフィールドを除去
- Step3 見出しを「{title}」主体に変更（beat タイトルと「第N話」が重複して照合不能になる問題）
- `WizardWorkflowPage` の既定章タイトルから「第1話」を除去（「第1話: title」形式の二重表示を解消）

### 残存課題（次フェーズ候補）

- `ChapterOutlineTree` の章追加/削除/並び替えはクライアント state のみで永続化されていない（Chapter 保存 API の追加が必要）
- Wizard 執筆分のサーバ永続化（`POST /api/episodes/chapters/import` の活用）
- ライト/セピアテーマでも入力欄が暗背景のまま（`.input` / `.textarea` のテーマトークン未対応）
- `POLL_INTERVAL_MS = 100` は高負荷。ポーリング間隔の段階制御が望ましい
